"""Interrupted evidence jobs retain their originals and can be reprocessed."""

from uuid import UUID

from sqlalchemy import select

from darknetra.audit.models import AuditEvent
from darknetra.auth.actor import Actor
from darknetra.cases.models import Case
from darknetra.evidence.models import CustodyEvent, Evidence
from darknetra.evidence.service import ingest_bytes
from darknetra.evidence.vault import LocalVault


async def create_case(client, title):
    response = await client.post("/api/v1/cases", json={"title": title, "demo": True})
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


async def test_interrupted_processing_is_audited_case_scoped_and_reprocessable(
    app, client, actor_login
):
    user = await actor_login()
    case_id = await create_case(client, "SYNTHETIC interrupted evidence")
    other_case_id = await create_case(client, "SYNTHETIC separate processing")
    actor = Actor("USER", user.id, user.global_role, user_id=user.id)
    async with app.state.session_factory() as db:
        pending = []
        for identifier in (case_id, other_case_id):
            case = await db.scalar(select(Case).where(Case.id == identifier))
            result = await ingest_bytes(
                db,
                case=case,
                actor=actor,
                data=b"SYNTHETIC original chitta source",
                filename="SYNTHETIC.txt",
                settings=app.state.settings,
                source_class="SYNTHETIC",
                defer_processing=True,
            )
            assert result.evidence.status == "PROCESSING"
            pending.append(result.evidence.id)
        case = await db.scalar(select(Case).where(Case.id == case_id))
        complete = await ingest_bytes(
            db,
            case=case,
            actor=actor,
            data=b"SYNTHETIC already complete source",
            filename="SYNTHETIC-complete.txt",
            settings=app.state.settings,
            source_class="SYNTHETIC",
        )
        quarantined = await ingest_bytes(
            db,
            case=case,
            actor=actor,
            data=b"SYNTHETIC unavailable format",
            filename="SYNTHETIC.exe",
            settings=app.state.settings,
            source_class="SYNTHETIC",
            defer_processing=True,
        )
        assert complete.evidence.status == "READY"
        assert quarantined.evidence.status == "QUARANTINED"
        original = await db.scalar(
            select(Evidence).where(Evidence.case_id == case_id, Evidence.id == pending[0])
        )
        original.warnings = ["SYNTHETIC_EXISTING_WARNING"]
        snapshot = (original.sha256, original.storage_key, original.size_bytes, original.code)
        custody_before = list(
            await db.scalars(
                select(CustodyEvent.id)
                .where(CustodyEvent.case_id == case_id, CustodyEvent.evidence_id == original.id)
                .order_by(CustodyEvent.id)
            )
        )
        await db.commit()

    from darknetra.ingest.recovery import recover_interrupted_evidence

    async with app.state.session_factory() as db:
        assert await recover_interrupted_evidence(db, case_id) == 1
        await db.commit()
    async with app.state.session_factory() as db:
        assert await recover_interrupted_evidence(db, case_id) == 0
        await db.commit()
        original = await db.scalar(
            select(Evidence).where(Evidence.case_id == case_id, Evidence.id == pending[0])
        )
        assert original.status == "FAILED"
        assert original.warnings == ["SYNTHETIC_EXISTING_WARNING", "PROCESSING_INTERRUPTED"]
        assert (
            original.sha256,
            original.storage_key,
            original.size_bytes,
            original.code,
        ) == snapshot
        with LocalVault(app.state.settings.vault_path).open(original.storage_key) as stream:
            assert stream.read() == b"SYNTHETIC original chitta source"
        custody_after = list(
            await db.scalars(
                select(CustodyEvent.id)
                .where(CustodyEvent.case_id == case_id, CustodyEvent.evidence_id == original.id)
                .order_by(CustodyEvent.id)
            )
        )
        assert custody_after == custody_before
        assert (
            await db.scalar(
                select(Evidence.status).where(
                    Evidence.case_id == other_case_id, Evidence.id == pending[1]
                )
            )
            == "PROCESSING"
        )
        assert (
            await db.scalar(
                select(Evidence.status).where(
                    Evidence.case_id == case_id, Evidence.id == complete.evidence.id
                )
            )
            == "READY"
        )
        assert (
            await db.scalar(
                select(Evidence.status).where(
                    Evidence.case_id == case_id, Evidence.id == quarantined.evidence.id
                )
            )
            == "QUARANTINED"
        )
        audits = list(
            await db.scalars(
                select(AuditEvent).where(
                    AuditEvent.case_id == case_id,
                    AuditEvent.action == "evidence.processing_interrupted",
                )
            )
        )
        assert len(audits) == 1
        assert audits[0].actor_kind == "SYSTEM" and audits[0].target_id == original.id
        assert audits[0].detail["reason"] == "APPLICATION_RESTART"
        assert audits[0].detail["recovery"] == "reprocess" and audits[0].result_hash
    response = await client.post(f"/api/v1/cases/{case_id}/evidence/{pending[0]}/reprocess")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "READY"
    assert response.json()["sha256"] == snapshot[0]


async def test_recovery_uses_caller_transaction_for_state_and_audit(app, client, actor_login):
    user = await actor_login()
    case_id = await create_case(client, "SYNTHETIC recovery rollback")
    actor = Actor("USER", user.id, user.global_role, user_id=user.id)
    async with app.state.session_factory() as db:
        case = await db.scalar(select(Case).where(Case.id == case_id))
        item = await ingest_bytes(
            db,
            case=case,
            actor=actor,
            data=b"SYNTHETIC rollback original",
            filename="SYNTHETIC.txt",
            settings=app.state.settings,
            source_class="SYNTHETIC",
            defer_processing=True,
        )
        await db.commit()

    from darknetra.ingest.recovery import recover_interrupted_evidence

    async with app.state.session_factory() as db:
        assert await recover_interrupted_evidence(db, case_id) == 1
        await db.rollback()
    async with app.state.session_factory() as db:
        assert (
            await db.scalar(
                select(Evidence.status).where(
                    Evidence.case_id == case_id, Evidence.id == item.evidence.id
                )
            )
            == "PROCESSING"
        )
        assert (
            await db.scalar(
                select(AuditEvent.id).where(
                    AuditEvent.case_id == case_id,
                    AuditEvent.action == "evidence.processing_interrupted",
                )
            )
            is None
        )
