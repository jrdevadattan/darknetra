import pytest
from darknetra_api.db.session import async_session_factory


@pytest.mark.asyncio
async def test_database_connection() -> None:
    import sqlalchemy as sa

    async with async_session_factory() as session:
        result = await session.execute(sa.text("select 1"))
        assert result.scalar_one() == 1
