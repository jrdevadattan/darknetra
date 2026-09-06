"""M1/M2/M4: generated synthetic evidence enters via HTTP before deterministic review."""

import importlib.util
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from darknetra.analytics.models import LinkCandidate
from darknetra.api.v1.schemas.analytics import CorrelateRequest
from darknetra.auth.service import user_actor
from darknetra.extract.models import CanonicalEntity
from darknetra.tools.contracts import ToolContext
from darknetra.tools.impl.analytics import correlate_entities


async def test_synthetic_case_planted_pair_and_escrow_decoy(client, actor_login, app, tmp_path):
    spec = importlib.util.spec_from_file_location(
        "core_synthetic", Path(__file__).resolve().parents[3] / "data/synthetic/generator.py"
    )
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    bundle = tmp_path / "synthetic-bundle"
    manifest = generator.generate(bundle)
    user = await actor_login()
    response = await client.post(
        "/api/v1/cases", json={"title": "SYNTHETIC complete fixture", "demo": True}
    )
    case_id = response.json()["id"]
    for item in manifest["files"]:
        path = bundle / item["filename"]
        response = await client.post(
            f"/api/v1/cases/{case_id}/evidence",
            files={"files": (path.name, path.read_bytes())},
            data={"source_class": "SYNTHETIC", "source_family": item["source_family"]},
        )
        assert response.status_code == 201 and not response.json()["errors"], response.text
        await app.state.jobs.wait_all()
    response = await client.post(f"/api/v1/cases/{case_id}/analytics/correlate", json={})
    assert response.status_code == 200, response.text
    await app.state.jobs.wait_all()
    async with app.state.session_factory() as db:
        labels = {
            entity.id: entity.value
            for entity in await db.scalars(
                select(CanonicalEntity).where(
                    CanonicalEntity.case_id == UUID(case_id), CanonicalEntity.type == "VENDOR_ALIAS"
                )
            )
        }
        candidates = list(
            await db.scalars(select(LinkCandidate).where(LinkCandidate.case_id == UUID(case_id)))
        )
        by_pair = {
            frozenset((labels[row.subject_a_id], labels[row.subject_b_id])): row
            for row in candidates
        }
        planted = by_pair[frozenset(("synthetic_alias_a", "synthetic_alias_a_chat"))]
        assert planted.band == "STRONG", json.dumps(
            {"score": planted.score, "features": planted.features}
        )
        decoy = by_pair[frozenset(("synthetic_alias_a", "synthetic_alias_b"))]
        assert decoy.band == "WEAK"
        assert all(row.status == "PENDING" for row in candidates)
    current = (
        await correlate_entities(
            ToolContext(
                UUID(case_id), user_actor(user), app.state.session_factory, app.state.settings
            ),
            CorrelateRequest(),
        )
    ).model_dump()
    assert current["result"]["candidates_created"] == 0
    assert current["result"]["candidates_rescored"] == 0
    assert planted.id in {candidate["id"] for candidate in current["candidates"]}
