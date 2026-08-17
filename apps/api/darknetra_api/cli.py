import argparse
import asyncio
import getpass
import os
from uuid import uuid4

from darknetra_api.db.session import async_session_factory
from darknetra_api.services.bootstrap import BootstrapAdminExists, bootstrap_admin

_BOOTSTRAP_PASSWORD_ENV = "DARKNETRA_BOOTSTRAP_ADMIN_PASSWORD"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="darknetra-api")
    subcommands = parser.add_subparsers(dest="command", required=True)

    bootstrap = subcommands.add_parser(
        "bootstrap-admin", description="Create the one-time initial DARKNETRA administrator."
    )
    bootstrap.add_argument("--username", required=True)
    bootstrap.add_argument("--display-name")
    return parser


async def _run_bootstrap_admin(username: str, display_name: str | None) -> None:
    password = os.environ.get(_BOOTSTRAP_PASSWORD_ENV)
    if password is None:
        password = getpass.getpass("Bootstrap administrator password: ")

    async with async_session_factory() as session:
        try:
            await bootstrap_admin(
                session,
                username=username,
                password=password,
                display_name=display_name or username,
                request_id=f"bootstrap-cli-{uuid4()}",
            )
            await session.commit()
        except BootstrapAdminExists as exc:
            await session.rollback()
            raise SystemExit(str(exc)) from exc


def main() -> None:
    args = _build_parser().parse_args()
    if args.command == "bootstrap-admin":
        asyncio.run(_run_bootstrap_admin(args.username, args.display_name))


if __name__ == "__main__":
    main()
