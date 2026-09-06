"""Structured operational logging without request payloads or credentials."""

import logging
import re
import time
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from darknetra.audit.service import record
from darknetra.auth.actor import Actor


def mask_pii(value: str) -> str:
    value = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "***", value)
    value = re.sub(r"(?<!\w)(?:\+?\d[\d ()-]{8,}\d)(?!\w)", "***", value)
    return re.sub(r"(?i)(?:sk-|dk_)[A-Za-z0-9_-]{10,}", "***", value)


def redact_log(_logger, _method, event):
    def scrub(value):
        if isinstance(value, str):
            return mask_pii(value)
        if isinstance(value, dict):
            return {
                key: "***"
                if any(
                    part in key.casefold()
                    for part in (
                        "password",
                        "secret",
                        "authorization",
                        "token",
                        "cookie",
                        "api_key",
                    )
                )
                else scrub(item)
                for key, item in value.items()
            }
        if isinstance(value, (tuple, list)):
            return [scrub(item) for item in value]
        return value

    return scrub(event)


def configure_logging(level="INFO"):
    structlog.configure(
        processors=[
            redact_log,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
    )
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format="%(message)s")
    # These libraries can log complete provider URLs, query strings and headers.
    for name in ("httpx", "httpcore", "sqlalchemy.engine", "apscheduler.executors.default"):
        logging.getLogger(name).setLevel(logging.WARNING)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        supplied = request.headers.get("x-request-id", "")
        request_id = supplied if re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", supplied) else str(uuid4())
        request.state.request_id = request_id
        started = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        route = getattr(request.scope.get("route"), "path", "unmatched")
        metric = getattr(request.app.state, "request_latency", None)
        if metric is not None:
            metric.labels(route, str(response.status_code)).observe(time.monotonic() - started)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            actor = getattr(request.state, "actor", Actor("SYSTEM", None))
            case_id = getattr(request.state, "case_id", None)
            try:
                async with request.app.state.session_factory() as db:
                    await record(
                        db,
                        actor=actor,
                        action="http." + request.method.lower(),
                        case_id=case_id,
                        detail={"route": route, "status": response.status_code},
                        request_id=request_id,
                    )
                    await db.commit()
            except Exception as exc:
                structlog.get_logger().error(
                    "audit_http_failed", error_type=type(exc).__name__, request_id=request_id
                )
        structlog.get_logger().info(
            "http_request",
            request_id=request_id,
            route=route,
            status=response.status_code,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        return response
