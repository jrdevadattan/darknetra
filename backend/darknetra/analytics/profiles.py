"""Evidence-backed alias profiles, with explicit publisher/sender attribution."""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from darknetra.analytics.inputs import load_inputs
from darknetra.errors import NotFound
from darknetra.evidence.models import Derivative
from darknetra.evidence.service import get_text
from darknetra.evidence.vault import LocalVault
from darknetra.extract.models import CanonicalEntity

WALLETS = {"BTC_ADDRESS", "ETH_ADDRESS", "TRON_ADDRESS", "XMR_ADDRESS"}
CONTACTS = {"CONTACT_HANDLE", "EMAIL", "PHONE"}


@dataclass
class AliasProfile:
    id: UUID
    value: str
    evidence_ids: set[UUID] = field(default_factory=set)
    fingerprints: dict[str, set[UUID]] = field(default_factory=dict)
    contacts: dict[str, set[UUID]] = field(default_factory=dict)
    wallets: dict[str, set[UUID]] = field(default_factory=dict)
    wallet_tags: dict[str, str] = field(default_factory=dict)
    image_hashes: dict[str, set[UUID]] = field(default_factory=dict)
    texts: list[tuple[UUID, str]] = field(default_factory=list)
    timestamps: list[datetime] = field(default_factory=list)
    locations: dict[str, set[UUID]] = field(default_factory=dict)
    platforms: set[str] = field(default_factory=set)
    terms: set[str] = field(default_factory=set)
    prices: list[float] = field(default_factory=list)

    def support(self) -> set[UUID]:
        result = set(self.evidence_ids)
        for signals in (
            self.fingerprints,
            self.contacts,
            self.wallets,
            self.image_hashes,
            self.locations,
        ):
            for ids in signals.values():
                result.update(ids)
        result.update(eid for eid, _ in self.texts)
        return result


def value_of(observation) -> str:
    normalized = observation.normalized
    if isinstance(normalized, dict):
        return str(normalized.get("value", observation.raw))
    return str(normalized)


def timestamp_of(observation, fallback: datetime) -> datetime:
    value = observation.meta.get("timestamp")
    if value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
        except ValueError:
            pass
    return fallback.astimezone(UTC)


async def build_profiles(session, case_id: UUID, settings=None) -> list[AliasProfile]:
    from darknetra.analytics.models import LedgerAddress

    evidence, observations = await load_inputs(session, case_id)
    entities = {
        r.id: r
        for r in await session.scalars(
            select(CanonicalEntity).where(
                CanonicalEntity.case_id == case_id,
                CanonicalEntity.type.in_(["VENDOR_ALIAS", "CONTACT_HANDLE"]),
            )
        )
    }
    profiles: dict[UUID, AliasProfile] = {}
    contexts = defaultdict(list)
    for obs in observations:
        entity = entities.get(obs.canonical_entity_id)
        if entity is None or (entity.type == "CONTACT_HANDLE" and obs.meta.get("role") != "sender"):
            continue
        # A vendor mention without publisher/sender attribution is not authorship.
        if obs.meta.get("role") not in {"sender", "publisher"}:
            continue
        profile = profiles.setdefault(entity.id, AliasProfile(entity.id, entity.value))
        profile.evidence_ids.add(obs.evidence_id)
        profile.timestamps.append(timestamp_of(obs, evidence[obs.evidence_id].captured_at))
        if platform := obs.meta.get("platform"):
            profile.platforms.add(str(platform))
        span = obs.meta.get("context_span")
        if (
            isinstance(span, dict)
            and isinstance(span.get("start"), int)
            and isinstance(span.get("end"), int)
            and 0 <= span["start"] < span["end"]
        ):
            contexts[obs.evidence_id].append((profile, span["start"], span["end"]))
    tags = {
        r.address: r.tag
        for r in await session.scalars(
            select(LedgerAddress).where(LedgerAddress.case_id == case_id)
        )
    }
    for obs in observations:
        owners = {
            p.id: p
            for p, start, end in contexts[obs.evidence_id]
            if start <= obs.span_start
            and obs.span_end <= end
            and (not obs.meta.get("subject_value") or obs.meta["subject_value"] == p.value)
        }
        # Overlapping contexts are ambiguous: never distribute a signal to all authors.
        if len(owners) != 1:
            continue
        profile = next(iter(owners.values()))
        value, target = value_of(obs), None
        if obs.type == "PGP_FINGERPRINT" and obs.validator == "pgpy_computed":
            target = profile.fingerprints
        elif obs.type in CONTACTS and obs.meta.get("role") != "sender":
            target = profile.contacts
        elif obs.type in WALLETS:
            target = profile.wallets
            profile.wallet_tags[value] = str(tags.get(value) or obs.meta.get("tag") or "unknown")
        elif obs.type == "LOCATION":
            target = profile.locations
        elif obs.type in {"SUBSTANCE", "SLANG", "SLANG_CANDIDATE"}:
            profile.terms.add(value)
        elif obs.type == "IMAGE_REFERENCE" and obs.meta.get("phash"):
            target, value = profile.image_hashes, str(obs.meta["phash"])
        if target is not None:
            target.setdefault(value, set()).add(obs.evidence_id)
    if settings:
        for eid, spans in contexts.items():
            try:
                text, _ = await get_text(session, case_id, eid, settings)
            except (NotFound, FileNotFoundError):
                continue
            seen = set()
            for profile, start, end in spans:
                if (profile.id, start, end) not in seen and end <= len(text):
                    profile.texts.append((eid, text[start:end]))
                    seen.add((profile.id, start, end))
        # Whole-document image metadata applies only to an unambiguous publisher.
        for derivative in await session.scalars(
            select(Derivative)
            .where(
                Derivative.case_id == case_id,
                Derivative.kind == "IMAGE_META",
                Derivative.status == "READY",
            )
            .order_by(Derivative.version.desc())
        ):
            owners = {p.id: p for p, _, _ in contexts[derivative.evidence_id]}
            if len(owners) != 1:
                continue
            try:
                with LocalVault(settings.vault_path).open(derivative.storage_key) as stream:
                    phash = json.load(stream).get("phash")
                if phash:
                    next(iter(owners.values())).image_hashes.setdefault(phash, set()).add(
                        derivative.evidence_id
                    )
            except (FileNotFoundError, ValueError, KeyError):
                continue
    return sorted(profiles.values(), key=lambda p: p.id)
