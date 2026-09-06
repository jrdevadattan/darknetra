"""Background tools recheck current user and credential state even on cache hits."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from darknetra.audit.models import AuditEvent
from darknetra.auth.actor import Actor
from darknetra.auth.models import ApiToken, Session, User
from darknetra.auth.service import user_actor
from darknetra.tools.contracts import ToolContext
from darknetra.tools.invoke import invoke


@pytest.mark.parametrize("change", ["disabled", "password", "role", "session", "token"])
async def test_revocation_blocks_next_cached_tool(client, actor_login, app, change):
    user = await actor_login()
    case_id = UUID(
        (
            await client.post("/api/v1/cases", json={"title": "SYNTHETIC revocation", "demo": True})
        ).json()["id"]
    )
    actor = user_actor(user)
    async with app.state.session_factory() as db:
        if change == "session":
            credential = await db.scalar(select(Session).where(Session.user_id == user.id))
            actor = user_actor(user, credential.id)
        elif change == "token":
            credential = ApiToken(
                id=uuid4(),
                name="SYNTHETIC token",
                owner_user_id=user.id,
                token_hash=uuid4().hex,
                scopes=["threads:run", "cases:read"],
                case_id=case_id,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            db.add(credential)
            await db.commit()
            actor = Actor(
                "TOKEN",
                credential.id,
                user.global_role,
                frozenset(credential.scopes),
                user_id=user.id,
                token_case_id=case_id,
            )
    ctx = ToolContext(case_id, actor, app.state.session_factory, app.state.settings)
    assert (await invoke(ctx, "search_evidence", {"query": "SYNTHETIC"})).ok
    assert ctx.cache
    async with app.state.session_factory() as db:
        current = await db.get(User, user.id)
        if change == "disabled":
            current.is_active = False
        elif change == "password":
            current.must_change_password = True
        elif change == "role":
            current.global_role = "VIEWER"
        else:
            current_credential = await db.get(
                Session if change == "session" else ApiToken, credential.id
            )
            current_credential.revoked_at = datetime.now(UTC)
        await db.commit()
    result = await invoke(ctx, "search_evidence", {"query": "SYNTHETIC"})
    assert not result.ok and result.error["code"] == "POLICY_DENIED"
    async with app.state.session_factory() as db:
        events = list(
            await db.scalars(
                select(AuditEvent).where(
                    AuditEvent.case_id == case_id, AuditEvent.action == "tool.call"
                )
            )
        )
        assert any(row.detail["status"] == "DENIED" for row in events)
