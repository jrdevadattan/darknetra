"""Reindex one authorised case without replacing evidence or derivative history."""

import argparse
import asyncio
import json
from uuid import UUID

from sqlalchemy import select

from darknetra.audit.service import record
from darknetra.auth.models import User
from darknetra.auth.service import user_actor
from darknetra.authz.deps import visible_case
from darknetra.authz.permissions import Permission, permitted
from darknetra.config import get_settings
from darknetra.db import build_engine, build_session_factory
from darknetra.errors import Forbidden
from darknetra.evidence.models import Derivative, Evidence
from darknetra.rag.index import index_evidence


async def reindex(case_id, actor_id):
    settings = get_settings()
    engine = build_engine(settings)
    factory = build_session_factory(engine)
    results = []
    try:
        async with factory() as db:
            actor_row = await db.get(User, actor_id)
            if not actor_row or not actor_row.is_active or actor_row.must_change_password:
                raise Forbidden("Active operator required")
            actor = user_actor(actor_row)
            _, role = await visible_case(db, actor, case_id)
            if not permitted(actor.global_role, role, Permission.EVIDENCE_UPLOAD):
                raise Forbidden("Evidence processing permission required")
            identifiers = list(
                await db.scalars(
                    select(Evidence.id)
                    .join(
                        Derivative,
                        (Derivative.case_id == Evidence.case_id)
                        & (Derivative.evidence_id == Evidence.id),
                    )
                    .where(
                        Evidence.case_id == case_id,
                        Evidence.status.in_(["READY", "PARTIAL"]),
                        Derivative.kind == "TEXT",
                    )
                    .distinct()
                )
            )
        for evidence_id in identifiers:
            async with factory() as db:
                stats = await index_evidence(db, case_id, evidence_id, settings)
                await record(
                    db,
                    actor=actor,
                    case_id=case_id,
                    action="retrieval.reindex",
                    target_type="evidence",
                    target_id=evidence_id,
                    detail=stats,
                )
                await db.commit()
                results.append({"evidence_id": str(evidence_id), **stats})
        print(json.dumps({"case_id": str(case_id), "results": results}))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", type=UUID, required=True)
    parser.add_argument("--actor-id", type=UUID, required=True)
    args = parser.parse_args()
    asyncio.run(reindex(args.case_id, args.actor_id))
