"""Narrative is optional; every proposed sentence passes the shared claim checker."""

from darknetra.agent.claim_checker import extract_claims, verify


async def checked_narrative(db, case_id, text):
    _, claims = extract_claims(text)
    await verify(db, case_id, claims)
    accepted, dropped = [], []
    for claim in claims:
        if claim.verified:
            accepted.append(
                {"text": claim.text, "evidence_codes": claim.evidence_codes, "kind": claim.kind}
            )
        else:
            # Store a reason, never the uncited potentially sensitive model sentence.
            dropped.append(claim.reason or "Unverified narrative was dropped")
    return accepted, dropped
