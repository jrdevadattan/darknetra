from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.api.v1.schemas.common import Page
from darknetra.api.v1.schemas.plugins import Plugin, PluginPatch
from darknetra.audit.service import record
from darknetra.authz.deps import current_actor, require, require_case
from darknetra.authz.permissions import Permission
from darknetra.db import get_session
from darknetra.errors import Conflict, NotFound
from darknetra.plugins.catalog import catalog, enabled, states
from darknetra.settings.models import Setting

router = APIRouter(tags=["plugins"])


async def inventory(db, settings, policy=None):
    configured = await states(db)
    items = []
    for name, manifest in catalog().items():
        active = enabled(manifest, configured.get(name)) and (
            policy is None
            or policy.get("enabled_plugins") is None
            or name in policy["enabled_plugins"]
        )
        status = (
            "disabled"
            if not active
            else "unavailable"
            if manifest["unavailable_reason"]
            else (
                "disabled_by_mode"
                if settings.offline_mode and manifest["requires_network"]
                else "not_probed"
                if manifest["requires_network"]
                else "ready"
            )
        )
        items.append(Plugin(**manifest, enabled=active, status=status))
    return Page(items=items)


@router.get("/plugins", response_model=Page[Plugin])
async def list_plugins(
    request: Request,
    actor=Depends(current_actor),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    return await inventory(db, request.app.state.settings)


@router.get("/cases/{case_id}/plugins", response_model=Page[Plugin])
async def case_plugins(
    request: Request,
    access=Depends(require_case(Permission.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    return await inventory(db, request.app.state.settings, access[1].source_policy)


@router.patch("/admin/plugins/{plugin_id}", response_model=Plugin)
async def configure_plugin(
    plugin_id: str,
    body: PluginPatch,
    request: Request,
    actor=Depends(require(Permission.ADMIN_SETTINGS)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    manifests = catalog()
    if plugin_id not in manifests:
        raise NotFound("Reviewed plugin not found")
    if body.manifest_hash != manifests[plugin_id]["manifest_hash"]:
        raise Conflict("Plugin manifest changed; review the current catalog")
    from sqlalchemy.dialects.postgresql import insert

    values = {"key": "plugin:" + plugin_id, "value": body.model_dump()}
    await db.execute(
        insert(Setting)
        .values(**values)
        .on_conflict_do_update(index_elements=[Setting.key], set_={"value": values["value"]})
    )
    await record(
        db,
        actor=actor,
        action="plugin.configure",
        target_type="plugin",
        detail={"plugin_id": plugin_id, **body.model_dump()},
    )
    await db.commit()
    return next(
        p for p in (await inventory(db, request.app.state.settings)).items if p.id == plugin_id
    )
