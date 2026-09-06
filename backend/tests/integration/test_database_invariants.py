"""Scenario 1, 8 and 44: ordering, runtime permissions, immutable audit history."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from darknetra.audit.models import AuditEvent


async def test_request_commits_case_lock_before_http_audit(client, app, actor_login):
    import asyncio
    from uuid import UUID

    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession

    from darknetra.authz.deps import require_case
    from darknetra.authz.permissions import Permission
    from darknetra.cases.models import Case
    from darknetra.db import get_session

    @app.post("/api/v1/cases/{case_id}/synthetic-commit-check")
    async def locked_mutation(
        case_id: UUID,
        access=Depends(require_case(Permission.THREAD_RUN)),
        db: AsyncSession = Depends(get_session, scope="function"),
    ):
        row = await db.scalar(select(Case).where(Case.id == case_id).with_for_update())
        row.scope_notes = "SYNTHETIC committed before response"
        await db.flush()
        return {"ok": True}

    await actor_login()
    case = (await client.post("/api/v1/cases", json={"title": "SYNTHETIC commit boundary"})).json()
    async with asyncio.timeout(10):
        response = await client.post(f"/api/v1/cases/{case['id']}/synthetic-commit-check")
    assert response.status_code == 200, response.text
    async with app.state.session_factory() as db:
        assert (
            await db.get(Case, UUID(case["id"]))
        ).scope_notes == "SYNTHETIC committed before response"
        assert await db.scalar(
            select(AuditEvent.id).where(
                AuditEvent.case_id == UUID(case["id"]),
                AuditEvent.action == "http.post",
                AuditEvent.request_id == response.headers["X-Request-ID"],
            )
        )


async def test_audit_append_only_even_for_database_owner(client, app, actor_login):
    await actor_login()
    case = (await client.post("/api/v1/cases", json={"title": "SYNTHETIC immutable audit"})).json()
    async with app.state.session_factory() as db:
        event = await db.scalar(select(AuditEvent).where(AuditEvent.case_id == case["id"]))
        assert event
        for statement in (
            "UPDATE audit_events SET action='tampered' WHERE id=:id",
            "DELETE FROM audit_events WHERE id=:id",
        ):
            with pytest.raises(DBAPIError):
                async with db.begin_nested():
                    await db.execute(text(statement), {"id": event.id})
        assert (await db.get(AuditEvent, event.id)).action == event.action


async def test_runtime_role_cannot_change_custody_or_decisions(app):
    async with app.state.session_factory() as db:
        exists = await db.scalar(text("SELECT 1 FROM pg_roles WHERE rolname='darknetra_app'"))
        assert exists, "Run the development/test migration to create restricted role grants"
        for table in (
            "audit_events",
            "decisions",
            "custody_events",
            "derivatives",
            "reports",
            "evidence",
        ):
            allowed = await db.scalar(
                text("SELECT has_table_privilege('darknetra_app', :table, 'DELETE')"),
                {"table": table},
            )
            assert not allowed, table
        assert not await db.scalar(
            text("SELECT has_table_privilege('darknetra_app', 'decisions', 'UPDATE')")
        )
        assert await db.scalar(
            text("SELECT has_table_privilege('darknetra_app', 'case_memberships', 'DELETE')")
        )
        assert await db.scalar(
            text("SELECT has_table_privilege('darknetra_app', 'taxonomy_terms', 'DELETE')")
        )


async def test_audit_cursor_preserves_descending_time_and_case_filter(client, actor_login):
    await actor_login()
    case = (await client.post("/api/v1/cases", json={"title": "SYNTHETIC ordered audit"})).json()
    for index in range(3):
        response = await client.patch(
            f"/api/v1/cases/{case['id']}", json={"scope_notes": f"SYNTHETIC event {index}"}
        )
        assert response.status_code == 200
    entries, cursor = [], None
    for _ in range(20):
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        response = await client.get(f"/api/v1/cases/{case['id']}/audit", params=params)
        assert response.status_code == 200, response.text
        page = response.json()
        entries.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(entries) >= 4
    assert len({entry["id"] for entry in entries}) == len(entries)
    assert all(entry["case_id"] == case["id"] for entry in entries)
    assert [entry["at"] for entry in entries] == sorted(
        (entry["at"] for entry in entries), reverse=True
    )
    empty = await client.get(
        f"/api/v1/cases/{case['id']}/audit", params={"to": "2000-01-01T00:00:00Z"}
    )
    assert empty.status_code == 200 and empty.json()["items"] == []
    assert (await client.get("/api/v1/audit")).status_code == 403


async def test_browser_can_send_version_header_and_metrics_are_admin_only(client, app, actor_login):
    response = await client.options(
        "/api/v1/cases/00000000-0000-0000-0000-000000000000/decisions",
        headers={
            "Origin": app.state.settings.web_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token,if-match",
        },
    )
    assert response.status_code == 200
    assert (await client.get("/metrics")).status_code == 401
    await actor_login("ADMIN")
    metrics = await client.get("/api/v1/metrics")
    assert metrics.status_code == 200 and "darknetra_runs" in metrics.text
