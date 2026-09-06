"""Transactional signals with explicit news, legal, and medical negative context."""

import re
from dataclasses import dataclass

from darknetra.analytics.link_scoring import FeatureContribution

NEGATIVE = (
    "seized",
    "seizure",
    "arrested",
    "police",
    "ncb",
    "court",
    "judgment",
    "study",
    "research",
    "hospital",
    "prescription",
    "overdose awareness",
    "news",
    "reported",
    "जब्त",
    "गिरफ्तार",
    "पुलिस",
    "अदालत",
    "ਜ਼ਬਤ",
    "ਪੁਲਿਸ",
)
OFFERS = ("available", "dm", "price", "delivery", "order", "milega", "bhej", "cod", "stock")
SIGNALS = {
    "substance": (0.45, {"SUBSTANCE", "SLANG"}),
    "quantity": (0.15, {"QUANTITY"}),
    "price_payment": (0.10, {"PRICE", "CURRENCY"}),
    "shipping": (0.10, {"SHIPPING_TERM"}),
    "contact_crypto": (
        0.10,
        {"CONTACT_HANDLE", "EMAIL", "PHONE", "BTC_ADDRESS", "ETH_ADDRESS", "TRON_ADDRESS"},
    ),
}


def negative_context(text):
    value = text.casefold()

    def present(cue):
        return re.search(r"(?<!\w)" + re.escape(cue) + r"(?!\w)", value) is not None

    cues, offers = [c for c in NEGATIVE if present(c)], [c for c in OFFERS if present(c)]
    penalty = (
        0.5 if len(cues) >= 2 and not offers else 0.25 if cues and len(cues) >= len(offers) else 0.0
    )
    return penalty, cues


@dataclass
class ActivityScore:
    score: float
    label: str
    features: list[FeatureContribution]


def score_signals(signals, text, evidence_ids=None, listing_context=False):
    evidence_ids = evidence_ids or []
    features = []
    for name, (weight, types) in SIGNALS.items():
        value = max((signals.get(t, 0.0) for t in types), default=0.0)
        features.append(
            FeatureContribution(
                name=name,
                family="TRANSACTIONAL",
                value=value,
                weight=weight,
                contribution=value * weight,
                evidence_ids=evidence_ids,
                explanation="maximum_validated_observation_confidence" if value else "not_observed",
            )
        )
    offer = any(re.search(r"(?<!\w)" + re.escape(c) + r"(?!\w)", text.casefold()) for c in OFFERS)
    value = float(listing_context or offer)
    features.append(
        FeatureContribution(
            name="listing_context",
            family="CONTEXT",
            value=value,
            weight=0.1,
            contribution=0.1 * value,
            evidence_ids=evidence_ids,
            explanation="explicit_listing_or_offer_context" if value else "not_observed",
        )
    )
    penalty, cues = negative_context(text)
    features.append(
        FeatureContribution(
            name="negative_context",
            family="CONTEXT",
            value=penalty,
            weight=-1.0,
            contribution=-penalty,
            evidence_ids=evidence_ids,
            explanation=", ".join(cues) or "no_negative_cue",
        )
    )
    rank = min(1.0, max(0.0, sum(f.contribution for f in features)))
    label = "LOW_SIGNAL" if rank < 0.35 else "CANDIDATE" if rank <= 0.65 else "HIGH_PRIORITY_REVIEW"
    return ActivityScore(round(rank, 6), label, features)


def score_observations(text, observations, evidence_id):
    """Rank a listing, or the strongest cluster of at most five consecutive sender messages."""
    from collections import defaultdict

    contexts = set()
    for obs in observations:
        span = obs.meta.get("context_span", {})
        if obs.meta.get("role") == "sender" and 0 <= span.get("start", -1) < span.get(
            "end", -1
        ) <= len(text):
            contexts.add(
                (
                    span["start"],
                    span["end"],
                    obs.meta.get("subject_value", str(obs.canonical_entity_id)),
                )
            )
    clusters = []
    if contexts:
        current, owner = [], None
        for start, end, subject in sorted(contexts):
            if current and (subject != owner or len(current) >= 5):
                clusters.append(current)
                current = []
            owner = subject
            current.append((start, end))
        if current:
            clusters.append(current)
    else:
        clusters = [[(0, len(text))]]
    results = []
    for spans in clusters:
        local = [
            obs
            for obs in observations
            if any(start <= obs.span_start < obs.span_end <= end for start, end in spans)
        ]
        signals = defaultdict(float)
        for obs in local:
            signals[obs.type] = max(signals[obs.type], obs.confidence)
        result = score_signals(
            signals,
            "\n".join(text[start:end] for start, end in spans),
            [evidence_id],
            listing_context=any(o.meta.get("role") == "publisher" for o in local),
        )
        for feature in result.features:
            feature.explanation += (
                "; "
                + ("sender_cluster" if contexts else "document")
                + " spans="
                + ",".join(f"{start}:{end}" for start, end in spans)
            )
        results.append(result)
    return max(results, key=lambda result: result.score)
