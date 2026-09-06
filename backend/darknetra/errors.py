"""Stable public errors. Validation input and exception values are never exposed."""

import logging
import traceback
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class AppError(Exception):
    code = "INTERNAL"
    status = 500

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class Unauthenticated(AppError):
    code, status = "UNAUTHENTICATED", 401


class NotFound(AppError):
    code, status = "NOT_FOUND", 404


class Forbidden(AppError):
    code, status = "FORBIDDEN", 403


class Validation(AppError):
    code, status = "VALIDATION", 422


class Conflict(AppError):
    code, status = "CONFLICT", 409


class PolicyDenied(AppError):
    code, status = "POLICY_DENIED", 403


class NetworkRequired(AppError):
    code, status = "NETWORK_REQUIRED", 503


class BudgetExceeded(AppError):
    code, status = "BUDGET_EXCEEDED", 402


class RateLimited(AppError):
    code, status = "RATE_LIMITED", 429


class Unavailable(AppError):
    code, status = "UNAVAILABLE", 503


class Locked(AppError):
    code, status = "LOCKED", 423


class TooLarge(AppError):
    code, status = "VALIDATION", 413


class NotImplementedFeature(AppError):
    code, status = "NOT_IMPLEMENTED", 501


def register_error_handlers(app: FastAPI) -> None:
    def envelope(
        request: Request, code: str, message: str, status: int, detail: dict[str, Any] | None = None
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            headers={"X-Request-ID": getattr(request.state, "request_id", "unknown")},
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "detail": detail or {},
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
        )

    @app.exception_handler(AppError)
    async def application_error(request: Request, exc: AppError) -> JSONResponse:
        response = envelope(request, exc.code, exc.message, exc.status, exc.detail)
        if exc.status in {423, 429} and "retry_after_seconds" in exc.detail:
            response.headers["Retry-After"] = str(max(1, int(exc.detail["retry_after_seconds"])))
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
        return envelope(request, "VALIDATION", "Request validation failed", 422, {"errors": errors})

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return envelope(
            request,
            {401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "VALIDATION"}.get(
                exc.status_code, "INTERNAL"
            ),
            "Request could not be completed",
            exc.status_code,
        )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        logging.getLogger(__name__).error(
            "Unhandled %s; stack=%s",
            type(exc).__name__,
            "".join(traceback.format_tb(exc.__traceback__)),
        )
        return envelope(request, "INTERNAL", "An internal error occurred", 500)
