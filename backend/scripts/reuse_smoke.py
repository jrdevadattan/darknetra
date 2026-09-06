"""Benign live integration diagnostics, captured in a separate, then closed case.

Run inside the API container so the database and vault are the same deployment.
This deliberately enables networking for this process only. No model calls occur.
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

import darknetra.models  # noqa: F401
from darknetra.api.v1.schemas.cases import CaseCreate, SourcePolicy
from darknetra.auth.models import User
from darknetra.auth.service import user_actor
from darknetra.cases.service import create, transition
from darknetra.config import Settings
from darknetra.db import build_engine, build_session_factory
from darknetra.tools.contracts import ToolContext
from darknetra.tools.invoke import invoke


async def main(selected: list[str] | None = None, search_provider: str = "duckduckgo"):
    settings = Settings(offline_mode=False, scheduler_enabled=False)
    engine = build_engine(settings)
    factory = build_session_factory(engine)
    try:
        async with factory() as db:
            user = await db.scalar(select(User).where(User.username == "administrator"))
            if user is None or not user.is_active or user.must_change_password:
                raise SystemExit("A configured active administrator is required")
            actor = user_actor(user)
            policy = SourcePolicy()
            policy.allowed_source_classes.append("OSINT_DARK")
            case = await create(
                db,
                actor,
                CaseCreate(
                    title="Public software documentation integration diagnostics",
                    scope_notes="Benign project/documentation queries only. No model calls or target-site investigation.",
                    source_policy=policy,
                ),
                settings,
            )
            await db.commit()
        checks = [
            (
                "surface_search",
                {"query": "Python official documentation", "limit": 3, "provider": search_provider},
            ),
            ("rss_read", {"url": "https://www.djangoproject.com/rss/weblog/", "limit": 3}),
            ("public_page_read", {"url": "https://docs.python.org/3/tutorial/index.html"}),
            ("agent_reach_read", {"url": "https://docs.python.org/3/tutorial/index.html"}),
            ("robin_search", {"query": "Tor Project", "limit": 3}),
        ]
        if selected:
            checks = [(name, args) for name, args in checks if name in selected]
        report = {
            "at": datetime.now(UTC).isoformat(),
            "case_id": str(case.id),
            "case_code": case.code,
            "checks": [],
        }
        try:
            for name, arguments in checks:
                ctx = ToolContext(
                    case_id=case.id, actor=actor, session_factory=factory, settings=settings
                )
                result = await invoke(ctx, name, arguments)
                data = result.data or {}
                summary = {
                    "tool": name,
                    "ok": result.ok,
                    "error": result.error,
                    "evidence_ids": result.evidence_ids,
                    "result_count": len(data.get("hits", data.get("entries", []))),
                    "text_chars": len(data.get("text", "")),
                }
                report["checks"].append(summary)
                print(json.dumps(summary, default=str), flush=True)
        finally:
            async with factory() as db:
                await transition(
                    db, case, actor, "CLOSED", "Live documentation diagnostics completed"
                )
                await db.commit()
        output = Path("/tmp/darknetra-reuse-live.json")
        output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print("Report: " + str(output))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tools",
        nargs="+",
        choices=[
            "surface_search",
            "rss_read",
            "public_page_read",
            "agent_reach_read",
            "robin_search",
        ],
    )
    parser.add_argument(
        "--search-provider", choices=["duckduckgo", "searxng"], default="duckduckgo"
    )
    options = parser.parse_args()
    asyncio.run(main(options.tools, options.search_provider))
