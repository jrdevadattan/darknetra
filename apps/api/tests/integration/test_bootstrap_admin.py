import pytest
import sqlalchemy as sa
from darknetra_api.db.session import async_session_factory
from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.enums import GlobalRole
from darknetra_api.models.user import User
from darknetra_api.services.bootstrap import BootstrapAdminExists, bootstrap_admin
from sqlalchemy import select


@pytest.fixture(autouse=True)
async def clean_identity_tables() -> None:
    async with async_session_factory() as session:
        await session.execute(sa.text("DELETE FROM audit_events"))
        await session.execute(sa.text("DELETE FROM auth_sessions"))
        await session.execute(sa.text("DELETE FROM users"))
        await session.commit()
    yield
    async with async_session_factory() as session:
        await session.execute(sa.text("DELETE FROM audit_events"))
        await session.execute(sa.text("DELETE FROM auth_sessions"))
        await session.execute(sa.text("DELETE FROM users"))
        await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bootstrap_admin_is_one_time_and_audited_without_secrets() -> None:
    async with async_session_factory() as session:
        created = await bootstrap_admin(
            session,
            username="InitialAdmin",
            password="Bootstrap password 42!",
            display_name="Initial Administrator",
            request_id="bootstrap-test-request",
        )
        await session.commit()
        first_hash = created.password_hash

    async with async_session_factory() as session:
        stored = await session.scalar(
            select(User).where(User.username_normalized == "initialadmin")
        )
        assert stored is not None
        assert stored.is_active is True
        assert stored.must_change_password is True
        assert stored.global_roles == [GlobalRole.ADMIN]
        event = await session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "ADMIN_BOOTSTRAPPED")
        )
        assert event is not None
        metadata_text = repr(event.metadata_json).lower()
        assert "password" not in metadata_text
        assert "hash" not in metadata_text

    async with async_session_factory() as session:
        with pytest.raises(BootstrapAdminExists):
            await bootstrap_admin(
                session,
                username="INITIALADMIN",
                password="A completely different password 99!",
                display_name="Replacement",
                request_id="bootstrap-test-request-2",
            )
        await session.rollback()

    async with async_session_factory() as session:
        stored = await session.scalar(
            select(User).where(User.username_normalized == "initialadmin")
        )
        assert stored is not None
        assert stored.password_hash == first_hash
