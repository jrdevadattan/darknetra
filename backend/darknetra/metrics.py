"""Administrative metrics with bounded labels and no case identifiers."""

from datetime import UTC, datetime

from fastapi import Depends, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import func, select

from darknetra.agent.models import Run, ToolCall
from darknetra.authz.deps import require
from darknetra.authz.permissions import Permission
from darknetra.evidence.models import Evidence
from darknetra.monitor.models import Alert, WatchlistItem


def install_metrics(app):
    registry = CollectorRegistry()
    app.state.request_latency = Histogram(
        "darknetra_http_duration_seconds", "Request latency", ["route", "status"], registry=registry
    )
    counts = {
        name: Gauge(f"darknetra_{name}", description, labels, registry=registry)
        for name, description, labels in (
            ("runs", "Persisted runs by status", ["status"]),
            ("tool_calls", "Persisted tool calls by status", ["tool", "status"]),
            ("captures", "Captured evidence by source class", ["source"]),
            ("alerts", "Persisted alerts by kind", ["kind"]),
            ("scheduler_lag_seconds", "Oldest overdue active item", []),
            ("ingest_queue_size", "Evidence still processing", []),
        )
    }

    @app.get("/metrics", include_in_schema=False)
    @app.get("/api/v1/metrics", include_in_schema=False)
    async def metrics(request: Request, actor=Depends(require(Permission.ADMIN_SETTINGS))):
        async with request.app.state.session_factory() as db:
            for name, model, columns, filters in (
                ("runs", Run, [Run.status], []),
                ("tool_calls", ToolCall, [ToolCall.tool, ToolCall.status], []),
                (
                    "captures",
                    Evidence,
                    [Evidence.source_class],
                    [Evidence.origin.in_(["CAPTURE", "MONITOR"])],
                ),
                ("alerts", Alert, [Alert.kind], []),
            ):
                counts[name].clear()
                rows = (
                    await db.execute(
                        select(*columns, func.count())
                        .select_from(model)
                        .where(*filters)
                        .group_by(*columns)
                    )
                ).all()
                for row in rows:
                    counts[name].labels(*row[:-1]).set(row[-1])
            oldest = await db.scalar(
                select(func.min(WatchlistItem.next_run_at)).where(WatchlistItem.active.is_(True))
            )
            counts["scheduler_lag_seconds"].set(
                max(0, (datetime.now(UTC) - oldest).total_seconds()) if oldest else 0
            )
            counts["ingest_queue_size"].set(
                await db.scalar(
                    select(func.count())
                    .select_from(Evidence)
                    .where(Evidence.status == "PROCESSING")
                )
                or 0
            )
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
