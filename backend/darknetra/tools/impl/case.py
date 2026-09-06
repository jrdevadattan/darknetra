"""Read case changes and create evidence-backed packs through existing services."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from darknetra.api.v1.schemas import alerts as dto
from darknetra.api.v1.schemas import reports
from darknetra.authz.permissions import Permission
from darknetra.monitor.models import Alert
from darknetra.reports.models import Report
from darknetra.tools.contracts import ToolContext
from darknetra.tools.impl.evidence import Input
from darknetra.tools.impl.shared import authorize


class AlertInput(Input):
    status: Literal["OPEN", "ACKNOWLEDGED", "DISMISSED", "ESCALATED"] | None = None
    limit: int = Field(20, ge=1, le=100)


class AlertOutput(BaseModel):
    alerts: list[dto.Alert]
    truncated: bool


class ChangesInput(Input):
    since: datetime

    @field_validator("since")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("since must include a timezone")
        return value


async def list_alerts(ctx: ToolContext, args: BaseModel) -> BaseModel:
    from darknetra.monitor.alerts import alert_dto

    options = cast(AlertInput, args)
    serialize = cast(Callable[..., Awaitable[dto.Alert]], alert_dto)
    async with ctx.session_factory() as session:
        await authorize(ctx, session, Permission.ALERT_VIEW)
        query = select(Alert).where(Alert.case_id == ctx.case_id)
        if options.status:
            query = query.where(Alert.status == options.status)
        rows = list(
            (
                await session.scalars(
                    query.order_by(Alert.at.desc(), Alert.id).limit(options.limit + 1)
                )
            ).all()
        )
        return AlertOutput(
            alerts=[await serialize(session, row) for row in rows[: options.limit]],
            truncated=len(rows) > options.limit,
        )


async def changes_since(ctx: ToolContext, args: BaseModel) -> BaseModel:
    from darknetra.monitor.alerts import changes_since as changes

    service = cast(Callable[..., Awaitable[dto.Changes]], changes)
    async with ctx.session_factory() as session:
        await authorize(ctx, session, Permission.ALERT_VIEW)
        return await service(session, ctx.case_id, cast(ChangesInput, args).since)


async def build_investigation_pack(ctx: ToolContext, args: BaseModel) -> BaseModel:
    from darknetra.reports.service import generate, report_dto

    options = cast(reports.ReportRequest, args)
    service = cast(Callable[..., Awaitable[Report]], generate)
    serialize = cast(Callable[..., Awaitable[reports.Report]], report_dto)
    async with ctx.session_factory() as session:
        case = await authorize(ctx, session, Permission.REPORT_GENERATE)
        if not options.redact:
            await authorize(ctx, session, Permission.EXPORT)
        row = await service(
            session, case=case, actor=ctx.actor, options=options, settings=ctx.settings
        )
        result = await serialize(session, row)
        await session.commit()
    await ctx.emit(
        {
            "type": "store.changed",
            "data": {"case_id": str(ctx.case_id), "tables": ["reports", "evidence"]},
        }
    )
    return result
