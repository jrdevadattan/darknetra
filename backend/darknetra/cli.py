"""Local administrative bootstrap. Credentials are never printed."""

import argparse
import asyncio
import os

from sqlalchemy import func, select

import darknetra.models  # noqa: F401
from darknetra.audit.service import record
from darknetra.auth.actor import Actor
from darknetra.auth.models import User
from darknetra.auth.passwords import hash_password
from darknetra.config import get_settings
from darknetra.db import build_engine, build_session_factory


async def bootstrap_admin() -> None:
    password = os.getenv("DARKNETRA_BOOTSTRAP_ADMIN_PASSWORD", "")
    if len(password) < 12:
        raise SystemExit("Set DARKNETRA_BOOTSTRAP_ADMIN_PASSWORD to at least 12 characters.")
    engine = build_engine(get_settings())
    try:
        async with build_session_factory(engine)() as db:
            await db.execute(select(func.pg_advisory_xact_lock(1700000999)))
            existing = await db.scalar(select(User).where(User.username == "administrator"))
            if existing:
                print("Administrator already exists; credentials preserved.")
                return
            user = User(
                username="administrator",
                display_name="Administrator",
                global_role="ADMIN",
                must_change_password=True,
                password_hash=await asyncio.to_thread(hash_password, password),
            )
            db.add(user)
            await db.flush()
            await record(
                db,
                actor=Actor("SYSTEM", None),
                action="user.bootstrap",
                target_type="user",
                target_id=user.id,
            )
            await db.commit()
            print("Administrator created; password change required before case access.")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["bootstrap-admin"])
    parser.parse_args()
    asyncio.run(bootstrap_admin())


if __name__ == "__main__":
    main()
