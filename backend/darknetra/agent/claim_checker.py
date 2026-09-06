"""Conservative citation coverage and exact finding confirmation checks."""

import json
import re
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.api.v1.schemas.threads import Claim, Verification
from darknetra.decisions.models import Decision, Finding
from darknetra.evidence.models import Evidence

FENCE = re.compile(r"```claims\s*([\s\S]*?)```", re.IGNORECASE)
CODES = re.compile(r"\bE-\d+\b")
CITATION = re.compile(r"\[E-\d+[^\]]*\]")
STATUS_TEXT = frozenset(
    {
        "Insufficient evidence.",
        "No matching evidence was found.",
        "Run cancelled.",
        "The model is unavailable.",
        "Run failed.",
        "Budget exhausted.",
    }
)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", CITATION.sub("", text)).strip(' \n\t-*."“”').casefold()


def extract_claims(text: str) -> tuple[str, list[Claim]]:
    matches = list(FENCE.finditer(text))
    prose = FENCE.sub("", text).strip()
    claims: list[Claim] = []
    for match in matches:
        try:
            items = json.loads(match.group(1))
            if not isinstance(items, list):
                raise ValueError("claims must be a list")
            claims.extend(Claim.model_validate({**item, "verified": False}) for item in items)
        except (ValueError, TypeError, ValidationError):
            claims.append(
                Claim(
                    text="Malformed claims block", evidence_codes=[], kind="model", verified=False
                )
            )
    # Mask exact declared prose before sentence splitting: an attributed quote can
    # contain several source sentences. Anything appended outside that exact span
    # remains subject to the uncited-prose check, including on the same line.
    uncovered = prose
    for claim in claims:
        if claim.text.strip():
            pattern = r"(?<!\w)" + re.escape(claim.text.strip()) + r"(?!\w)"
            uncovered = re.sub(pattern, "\n", uncovered)
    for segment in re.split(r"\n+|(?<=[.!?\]])\s+(?=[A-Z])", uncovered):
        segment = segment.strip()
        if not segment or segment in STATUS_TEXT:
            continue
        normalized = normalize(segment)
        if not normalized:
            continue
        if matches and any(normalize(c.text) == normalized for c in claims):
            continue
        claims.append(
            Claim(
                text=segment,
                evidence_codes=sorted(set(CODES.findall(segment))),
                kind="observed",
                verified=False,
            )
        )
    return prose, claims


async def verify(
    session: AsyncSession, case_id: UUID, claims: list[Claim] | list[dict]
) -> Verification:
    parsed = [
        c if isinstance(c, Claim) else Claim.model_validate({**c, "verified": False})
        for c in claims
    ]
    codes = {code for claim in parsed for code in claim.evidence_codes}
    evidence = (
        list(
            (
                await session.scalars(
                    select(Evidence).where(Evidence.case_id == case_id, Evidence.code.in_(codes))
                )
            ).all()
        )
        if codes
        else []
    )
    by_code = {e.code: e for e in evidence if e.status not in {"QUARANTINED", "EXPIRED", "FAILED"}}
    findings = (
        list(
            (
                await session.scalars(
                    select(Finding).where(
                        Finding.case_id == case_id,
                        Finding.kind == "CONFIRMED",
                        Finding.status == "PROMOTED",
                    )
                )
            ).all()
        )
        if any(c.kind == "confirmed" for c in parsed)
        else []
    )
    for claim in parsed:
        claim.reason = None
        if not claim.evidence_codes or not claim.text.strip():
            claim.reason = "A factual claim requires evidence citations"
        elif any(code not in by_code for code in claim.evidence_codes):
            claim.reason = "Unknown, inaccessible, or quarantined evidence"
        elif claim.kind == "confirmed":
            ids = {by_code[code].id for code in claim.evidence_codes}
            accepted = False
            for finding in findings:
                if normalize(finding.claim) != normalize(claim.text) or not ids <= set(
                    finding.evidence_ids
                ):
                    continue
                decision = await session.scalar(
                    select(Decision).where(
                        Decision.case_id == case_id,
                        Decision.id == finding.decision_id,
                        Decision.decision == "ACCEPT",
                    )
                )
                if decision is not None:
                    superseding = await session.scalar(
                        select(Decision.id).where(
                            Decision.case_id == case_id, Decision.supersedes_id == decision.id
                        )
                    )
                    if superseding is None:
                        accepted = True
                        break
            if not accepted:
                claim.reason = "No current accepted finding matches this exact claim and evidence"
        claim.verified = claim.reason is None
    # Support report callers passing mutable DTO dictionaries as well.
    for original, checked in zip(claims, parsed, strict=True):
        if isinstance(original, dict):
            original.update(checked.model_dump(mode="json"))
    count = sum(not c.verified for c in parsed)
    return Verification(ok=count == 0, unverified_count=count, revised=False)
