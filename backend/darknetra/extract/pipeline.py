import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.audit.service import record
from darknetra.auth.actor import Actor
from darknetra.config import Settings
from darknetra.evidence.models import Evidence
from darknetra.extract.models import CanonicalEntity, ExtractionRun, Observation, TaxonomyTerm
from darknetra.extract.normalize import normalize, raw_span
from darknetra.extract.validators import Candidate, find_candidates

BUNDLE_VERSION = "deterministic-v2"


async def run_evidence(
    session: AsyncSession,
    case_id: UUID,
    evidence_id: UUID,
    settings: Settings,
    bundle_version: str | None = None,
) -> ExtractionRun:
    from darknetra.evidence.service import get_text

    evidence = await session.scalar(
        select(Evidence)
        .where(Evidence.case_id == case_id, Evidence.id == evidence_id)
        .with_for_update()
    )
    if evidence is None:
        from darknetra.errors import NotFound

        raise NotFound("Evidence not found")
    taxonomy = list(await session.scalars(select(TaxonomyTerm)))
    terms = [term for term in taxonomy if term.active]
    text, derivative = await get_text(session, case_id, evidence_id, settings)
    version = (
        bundle_version
        or BUNDLE_VERSION
        + ":"
        + hashlib.sha256(
            json.dumps(sorted((str(t.id), t.version, t.active) for t in taxonomy)).encode()
        ).hexdigest()[:12]
        + f":text{derivative.version}"
    )
    existing = await session.scalar(
        select(ExtractionRun).where(
            ExtractionRun.case_id == case_id,
            ExtractionRun.evidence_id == evidence_id,
            ExtractionRun.bundle_version == version,
        )
    )
    if existing:
        return existing
    now = datetime.now(UTC)
    run = ExtractionRun(
        case_id=case_id,
        evidence_id=evidence_id,
        bundle_version=version,
        status="RUNNING",
        started_at=now,
        stats={},
    )
    session.add(run)
    await session.flush()
    nt = normalize(text)
    import asyncio

    candidates = await asyncio.to_thread(find_candidates, nt.normalized)
    import re

    for term in terms:
        for match in re.finditer(
            r"(?<!\w)" + re.escape(normalize(term.term).normalized) + r"(?!\w)", nt.normalized, re.I
        ):
            candidates.append(
                Candidate(
                    term.type,
                    match[0],
                    {"value": term.canonical},
                    *match.span(),
                    "lexicon_exact",
                    True,
                    0.85,
                    {
                        "term_id": str(term.id),
                        "term_version": term.version,
                        "language": term.language,
                        "script": term.script,
                        "canonical": term.canonical,
                        "matched_variant": term.term,
                    },
                )
            )
    anchored = [
        (candidate, *raw_span(nt, candidate.start, candidate.end)) for candidate in candidates
    ]
    contexts = derivative.meta.get("contexts", [])
    for context in contexts:
        start, end = context["start"], context["end"]
        if not 0 <= start < end <= len(text) or text[start:end] != context["value"]:
            continue
        meta = {
            key: value for key, value in context.items() if key not in {"start", "end", "value"}
        }
        anchored.append(
            (
                Candidate(
                    "VENDOR_ALIAS",
                    text[start:end],
                    {"value": text[start:end].casefold()},
                    start,
                    end,
                    "parser_sender" if context["role"] == "sender" else "explicit_publisher",
                    meta=meta,
                ),
                start,
                end,
            )
        )
    counts = {}
    for candidate, start, end in anchored:
        raw = text[start:end]
        meta = dict(candidate.meta)
        owners = [
            context
            for context in contexts
            if context["context_span"]["start"] <= start < end <= context["context_span"]["end"]
        ]
        if len(owners) == 1:
            owner = owners[0]
            meta.update(
                {
                    "subject_value": owner["value"].casefold(),
                    **{
                        key: owner[key]
                        for key in ("context_span", "message_id", "timestamp", "platform")
                        if key in owner
                    },
                }
            )
        entity_id = None
        # Textual fingerprints and aliases do not establish identifier equivalence.
        eligible = candidate.valid and candidate.type not in {
            "PRICE",
            "QUANTITY",
            "PGP_KEY",
            "XMR_ADDRESS",
            "URL",
        }
        if eligible:
            value = candidate.normalized.get("value", raw.casefold())
            stmt = insert(CanonicalEntity).values(
                case_id=case_id,
                type=candidate.type,
                value=value,
                display=value,
                first_seen_at=evidence.captured_at,
                last_seen_at=evidence.captured_at,
                observation_count=1,
                attrs={},
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["case_id", "type", "value"],
                set_={
                    "observation_count": CanonicalEntity.observation_count + 1,
                    "last_seen_at": evidence.captured_at,
                },
            ).returning(CanonicalEntity.id)
            entity_id = await session.scalar(stmt)
        session.add(
            Observation(
                case_id=case_id,
                evidence_id=evidence_id,
                derivative_id=derivative.id,
                run_id=run.id,
                type=candidate.type,
                raw=raw,
                normalized=candidate.normalized,
                canonical_entity_id=entity_id,
                span_start=start,
                span_end=end,
                line_no=text.count("\n", 0, start) + 1,
                validator=candidate.validator,
                valid=candidate.valid,
                confidence=candidate.confidence,
                meta=meta,
            )
        )
        counts[candidate.type] = counts.get(candidate.type, 0) + 1
    run.status, run.finished_at = "DONE", datetime.now(UTC)
    run.stats = {
        "counts": counts,
        "ner": "unavailable",
        "warnings": list(nt.warnings),
        "observations": sum(counts.values()),
    }
    await record(
        session,
        actor=Actor("SYSTEM", None),
        action="extraction.run",
        case_id=case_id,
        target_type="extraction_run",
        target_id=run.id,
        detail=run.stats,
    )
    await session.flush()
    return run
