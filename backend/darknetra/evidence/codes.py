from sqlalchemy.dialects.postgresql import insert

from darknetra.evidence.models import EvidenceCodeCounter


async def next_evidence_code(session, case_id) -> str:
    stmt = insert(EvidenceCodeCounter).values(case_id=case_id, next=2)
    stmt = stmt.on_conflict_do_update(
        index_elements=["case_id"], set_={"next": EvidenceCodeCounter.next + 1}
    ).returning(EvidenceCodeCounter.next)
    number = await session.scalar(stmt)
    return f"E-{number - 1:04d}"
