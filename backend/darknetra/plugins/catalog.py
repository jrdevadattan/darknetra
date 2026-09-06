from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.api.v1.schemas.cases import SourcePolicy
from darknetra.audit.service import digest
from darknetra.settings.models import Setting
from darknetra.tools.contracts import ToolSpec
from darknetra.tools.presentation import tool_metadata
from darknetra.tools.registry import REGISTRY


@lru_cache(maxsize=1)
def implementation_identity() -> str:
    root = Path(__file__).resolve().parents[1]
    # A deployment's implementation, lockfile and upstream notices are part of review.
    files = sorted(root.rglob("*.py"))
    lock = root.parent / "uv.lock"
    if lock.is_file():
        files.append(lock)
    return digest(
        [str(p.relative_to(root.parent)) + "\n" + p.read_text(encoding="utf-8") for p in files]
    )


def catalog() -> dict[str, Any]:
    groups = defaultdict(list)
    for spec in REGISTRY.values():
        metadata = tool_metadata(spec)
        if metadata["integration_id"] != "darknetra":
            groups[metadata["integration_id"]].append(spec)
    return {
        name: {
            "id": name,
            "installed": True,
            "installation_kind": "bundled_reviewed",
            "manifest_hash": digest(
                [
                    {
                        "name": s.name,
                        "implementation": implementation_identity(),
                        "description": s.description,
                        "input": s.input_model.model_json_schema(),
                        "output": s.output_model.model_json_schema(),
                        "source_class": s.source_class,
                        "policy_tags": sorted(s.policy_tags),
                    }
                    for s in specs
                ]
            ),
            "tools": [s.name for s in specs],
            "requires_network": any(s.requires_network for s in specs),
            "unavailable_reason": next(
                (s.unavailable_reason for s in specs if s.unavailable_reason), None
            ),
        }
        for name, specs in sorted(groups.items())
    }


async def states(db):
    rows = await db.scalars(select(Setting).where(Setting.key.like("plugin:%")))
    return {r.key.partition(":")[2]: r.value for r in rows}


def enabled(manifest: dict[str, Any], state: Any) -> bool:
    if state is None:
        return True
    return (
        isinstance(state, dict)
        and state.get("enabled") is True
        and state.get("manifest_hash") == manifest["manifest_hash"]
    )


async def tool_enabled(
    db: AsyncSession, spec: ToolSpec, policy: SourcePolicy | None = None
) -> bool:
    name = tool_metadata(spec)["integration_id"]
    if name == "darknetra":
        return True
    manifest = catalog()[name]
    row = await db.get(Setting, "plugin:" + name)
    return enabled(manifest, row.value if row else None) and (
        policy is None or policy.enabled_plugins is None or name in policy.enabled_plugins
    )


async def disabled_tool_names(db: AsyncSession, policy: SourcePolicy) -> frozenset[str]:
    configured = await states(db)
    manifests = catalog()
    return frozenset(
        s.name
        for s in REGISTRY.values()
        if (name := tool_metadata(s)["integration_id"]) != "darknetra"
        and (
            not enabled(manifests[name], configured.get(name))
            or policy.enabled_plugins is not None
            and name not in policy.enabled_plugins
        )
    )
