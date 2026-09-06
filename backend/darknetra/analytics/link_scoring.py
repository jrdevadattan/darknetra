"""Explainable deterministic correlation, with negative controls and evidence lineage."""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from pydantic import BaseModel, Field

from darknetra.analytics.config import LinkConfig
from darknetra.analytics.profiles import AliasProfile
from darknetra.audit.service import digest


class FeatureContribution(BaseModel):
    name: str
    family: str
    value: float
    weight: float
    contribution: float
    evidence_ids: list[UUID] = Field(default_factory=list)
    explanation: str


@dataclass
class ScoredPair:
    score: int
    band: str
    families: list[str]
    features: list[FeatureContribution]
    contradictions: list[dict]
    meta: dict

    @property
    def feature_digest(self) -> str:
        return digest([f.model_dump(mode="json") for f in self.features])


def phash_distance(a: str, b: str) -> int:
    if len(a) != 16 or len(b) != 16:
        return 65
    try:
        return (int(a, 16) ^ int(b, 16)).bit_count()
    except ValueError:
        return 65


def clean_texts(corpus: list[AliasProfile]) -> dict[UUID, list[tuple[UUID, str]]]:
    counts = Counter(
        line.strip().casefold()
        for p in corpus
        for line in {
            line.strip().casefold()
            for _, text in p.texts
            for line in text.splitlines()
            if line.strip()
        }
    )
    return {
        p.id: [
            (
                eid,
                "\n".join(
                    line for line in text.splitlines() if counts[line.strip().casefold()] < 3
                ),
            )
            for eid, text in p.texts
        ]
        for p in corpus
    }


def grams(text: str) -> set[str]:
    words = re.findall(r"\w+", text.casefold())
    return {" ".join(words[i : i + 4]) for i in range(max(0, len(words) - 3))}


def score(
    a: AliasProfile, b: AliasProfile, config: LinkConfig | None = None, *, corpus=None
) -> ScoredPair:
    config, corpus = config or LinkConfig(), corpus or [a, b]
    features: list[FeatureContribution] = []
    both_support = a.support() | b.support()

    def add(name, family, value, ids, explanation):
        value = min(1.0, max(0.0, float(value)))
        # No positive signal without supporting source evidence.
        if value and not ids:
            value, explanation = 0.0, "insufficient_evidence"
        weight = config.weights[name]
        features.append(
            FeatureContribution(
                name=name,
                family=family,
                value=value,
                weight=weight,
                contribution=round(100 * value * weight, 6),
                evidence_ids=sorted(ids),
                explanation=explanation,
            )
        )

    def shared_signals(left, right):
        keys = set(left) & set(right)
        return keys, set().union(*(left[k] | right[k] for k in keys)) if keys else set()

    shared, ids = shared_signals(a.fingerprints, b.fingerprints)
    add(
        "pgp_fingerprint",
        "CRYPTOGRAPHIC_IDENTIFIER",
        bool(shared),
        ids,
        "shared_computed_fingerprint" if shared else "no_shared_computed_fingerprint",
    )
    shared, ids = shared_signals(a.wallets, b.wallets)
    usable = {
        w
        for w in shared
        if a.wallet_tags.get(w) not in {"shared_service", "escrow"}
        and b.wallet_tags.get(w) not in {"shared_service", "escrow"}
        and sum(w in p.wallets for p in corpus) < 3
    }
    wallet_ids = set().union(*(a.wallets[w] | b.wallets[w] for w in usable)) if usable else ids
    add(
        "wallet_reuse",
        "CONTACT_CRYPTO",
        bool(usable),
        wallet_ids,
        "shared_context_wallet" if usable else "shared_service" if shared else "no_shared_wallet",
    )
    shared, ids = shared_signals(a.contacts, b.contacts)
    add(
        "contact_reuse",
        "CONTACT_CRYPTO",
        bool(shared),
        ids,
        "shared_normalized_contact" if shared else "no_shared_contact",
    )
    image_pairs = sorted(
        (phash_distance(x, y), x, y) for x in a.image_hashes for y in b.image_hashes
    )
    value, ids, reason = 0.0, set(), "no_image_family"
    if image_pairs and image_pairs[0][0] <= 8:
        distance, x, y = image_pairs[0]
        value, ids, reason = (
            1 - distance / 16,
            a.image_hashes[x] | b.image_hashes[y],
            "perceptual_image_family",
        )
        prevalence = sum(
            any(min(phash_distance(h, x), phash_distance(h, y)) <= 8 for h in p.image_hashes)
            for p in corpus
        )
        if prevalence >= 4:
            value, reason = 0.2 * value, "stock_image_discount"
    add("image_family", "IMAGE", value, ids, reason)
    cleaned = clean_texts(corpus)
    left, right = cleaned.get(a.id, a.texts), cleaned.get(b.id, b.texts)
    left_text, right_text = "\n".join(t for _, t in left), "\n".join(t for _, t in right)
    ids = {eid for eid, text in left + right if text.strip()}
    style, reason = 0.0, "insufficient_evidence"
    if (
        len({eid for eid, text in left if text.strip()}) >= 2
        and len({eid for eid, text in right if text.strip()}) >= 2
        and min(len(left_text), len(right_text)) >= 300
    ):
        from sklearn.feature_extraction.text import TfidfVectorizer

        try:
            matrix = TfidfVectorizer(analyzer="char", ngram_range=(3, 5)).fit_transform(
                [left_text, right_text]
            )
            style, reason = (
                float((matrix[0] @ matrix[1].T).toarray()[0, 0]),
                "template_discounted_char_ngrams",
            )
        except ValueError:
            pass
    add("stylometry", "TEXT_STYLE", style, ids, reason)
    doc_grams = [grams(text) for texts in cleaned.values() for _, text in texts if text.strip()]
    frequencies = Counter(g for values in doc_grams for g in values)
    lg, rg = grams(left_text), grams(right_text)
    rare = {g for g in lg & rg if frequencies[g] <= 2}
    add(
        "rare_phrase",
        "TEXT_STYLE",
        len(rare) / max(1, min(len(lg), len(rg))),
        ids,
        "shared_rare_fourgrams" if rare else "no_shared_rare_phrase",
    )
    temporal, overlapping = 0.0, False
    if a.timestamps and b.timestamps:
        a0, a1, b0, b1 = min(a.timestamps), max(a.timestamps), min(b.timestamps), max(b.timestamps)
        overlapping = max(a0, b0) <= min(a1, b1)
        if overlapping:
            span = max((max(a1, b1) - min(a0, b0)).total_seconds(), 1)
            overlap = (min(a1, b1) - max(a0, b0)).total_seconds()
            temporal = 1.0 if span == 1 else max(0.0, overlap / span)
        elif min(abs(b0 - a1), abs(a0 - b1)) <= timedelta(days=7):
            temporal = 0.5
    add(
        "temporal",
        "TEMPORAL_OPERATIONAL",
        temporal,
        both_support,
        "overlapping_active_windows"
        if overlapping
        else "migration_window"
        if temporal
        else "insufficient_evidence",
    )
    shared_locations, location_ids = shared_signals(a.locations, b.locations)
    operational = len(shared_locations) / max(1, len(set(a.locations) | set(b.locations)))
    add(
        "operational",
        "TEMPORAL_OPERATIONAL",
        operational,
        location_ids,
        "shared_claimed_location" if shared_locations else "insufficient_evidence",
    )
    different_keys = (
        overlapping
        and a.fingerprints
        and b.fingerprints
        and not (set(a.fingerprints) & set(b.fingerprints))
    )
    same_week = any(abs(x - y) <= timedelta(days=7) for x in a.timestamps for y in b.timestamps)
    different_locations = same_week and a.locations and b.locations and not shared_locations
    contradictions = []
    if different_keys:
        contradictions.append({"reason": "different_computed_fingerprints_in_overlapping_windows"})
    if different_locations:
        contradictions.append({"reason": "different_claimed_locations_in_same_week"})
    add(
        "contradiction",
        "CONTRADICTION",
        bool(contradictions),
        both_support if contradictions else set(),
        "; ".join(x["reason"] for x in contradictions) or "none_observed",
    )
    rank = round(min(100.0, max(0.0, sum(f.contribution for f in features))))
    band = "WEAK" if rank < 40 else "POSSIBLE" if rank < 55 else "LEAD" if rank < 75 else "STRONG"
    families = sorted({f.family for f in features if f.contribution > 0})
    anchor = any(
        f.value > 0
        for f in features
        if f.name in {"pgp_fingerprint", "wallet_reuse", "contact_reuse", "image_family"}
    )
    meta = {"ranking_caveat": "engineering ranking; not a probability of identity or guilt"}
    if band == "STRONG" and (len(families) < 2 or not anchor):
        band, meta["capped_by"] = "LEAD", "independence_rule"
    return ScoredPair(rank, band, families, features, contradictions, meta)
