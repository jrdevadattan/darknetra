"""Deterministic review candidates; never changes the authoritative taxonomy."""

import hashlib
import math
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime

from sqlalchemy import select

from darknetra.audit.service import record
from darknetra.auth.actor import Actor
from darknetra.cases.models import Case
from darknetra.evidence.models import Evidence
from darknetra.evidence.service import get_text
from darknetra.extract.models import ExtractionRun, Observation, TaxonomyTerm
from darknetra.extract.validators import LEXICON

STOPWORDS = set(
    "synthetic sample exercise training only test classification example the this that with from have which where what for and not are was were you your mein hai ka ki ke se ko ko to aur sample police seized no offer sale price recorded real person identified purani cheez sender alias contact shared service escrow testnet wallet".split()
)


def entropy(token):
    counts = Counter(token)
    return -sum((count / len(token)) * math.log2(count / len(token)) for count in counts.values())


async def discover(session, case_id, settings):
    await session.scalar(select(Case.id).where(Case.id == case_id).with_for_update())
    known = {term.casefold() for _, terms in LEXICON.values() for term in terms}
    known.update(
        term.casefold()
        for term in await session.scalars(
            select(TaxonomyTerm.term).where(TaxonomyTerm.active.is_(True))
        )
    )
    frequencies, occurrences = Counter(), defaultdict(list)
    evidence_rows = await session.scalars(
        select(Evidence).where(
            Evidence.case_id == case_id, Evidence.status.in_(["READY", "PARTIAL"])
        )
    )
    from darknetra.errors import NotFound

    for evidence in evidence_rows:
        try:
            text, derivative = await get_text(session, case_id, evidence.id, settings)
        except NotFound:
            continue
        excluded = list(
            await session.execute(
                select(Observation.span_start, Observation.span_end).where(
                    Observation.case_id == case_id,
                    Observation.evidence_id == evidence.id,
                    Observation.derivative_id == derivative.id,
                    Observation.type != "SLANG_CANDIDATE",
                )
            )
        )
        for match in re.finditer(r"[^\W\d_]{4,20}", text, re.UNICODE):
            term = match[0].casefold()
            if term in STOPWORDS or term in known or (term.isascii() and entropy(term) > 3.5):
                continue
            if any(match.start() < end and match.end() > start for start, end in excluded):
                continue
            frequencies[term] += 1
            occurrences[term].append(
                (
                    evidence,
                    derivative,
                    match.start(),
                    match.end(),
                    match[0],
                    text.count("\n", 0, match.start()) + 1,
                )
            )
    selected = {
        term: rows
        for term, rows in occurrences.items()
        if frequencies[term] >= 3 and len({row[0].id for row in rows}) >= 2
    }
    if not selected:
        return []
    version = (
        "novel-v1:"
        + hashlib.sha256(
            repr(sorted((term, frequencies[term]) for term in selected)).encode()
        ).hexdigest()[:16]
    )
    existing = await session.scalar(
        select(ExtractionRun).where(
            ExtractionRun.case_id == case_id,
            ExtractionRun.evidence_id.is_(None),
            ExtractionRun.bundle_version == version,
        )
    )
    if existing:
        return []
    now = datetime.now(UTC)
    run = ExtractionRun(
        case_id=case_id,
        evidence_id=None,
        bundle_version=version,
        status="DONE",
        started_at=now,
        finished_at=now,
        stats={"novel_terms": len(selected)},
    )
    session.add(run)
    await session.flush()
    observations = []
    for term, rows in selected.items():
        evidence, derivative, start, end, raw, line = rows[0]
        diversity = len({row[0].id for row in rows})
        observation = Observation(
            case_id=case_id,
            evidence_id=evidence.id,
            derivative_id=derivative.id,
            run_id=run.id,
            type="SLANG_CANDIDATE",
            raw=raw,
            normalized={"value": term},
            span_start=start,
            span_end=end,
            line_no=line,
            validator="novel_term_frequency",
            valid=False,
            confidence=0.5,
            meta={
                "frequency": frequencies[term],
                "diversity": diversity,
                "score": math.log1p(frequencies[term]) * diversity,
                "review_required": True,
            },
        )
        session.add(observation)
        observations.append(observation)
    await record(
        session,
        actor=Actor("SYSTEM", None),
        action="extraction.novel_terms",
        case_id=case_id,
        target_type="extraction_run",
        target_id=run.id,
        detail=run.stats,
    )
    return observations
