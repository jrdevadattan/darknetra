from typing import Annotated
from uuid import uuid4

from darknetra_api.config import get_settings
from darknetra_api.db.session import get_db_session
from darknetra_api.models.user import User
from darknetra_api.schemas.auth import (
    AuthResponse,
    AuthUserResponse,
    ChangePasswordRequest,
    LoginRequest,
)
from darknetra_api.security.passwords import PasswordPolicyError
from darknetra_api.services.auth import (
    AuthContext,
    AuthenticationError,
    CsrfError,
    IssuedSession,
    LoginRateLimited,
    change_password,
    get_auth_context,
    login,
    logout,
    refresh,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["auth"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]

ACCESS_COOKIE = "darknetra_access"
REFRESH_COOKIE = "darknetra_refresh"
CSRF_COOKIE = "darknetra_csrf"
ACCESS_MAX_AGE = 900
REFRESH_MAX_AGE = 28800


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-ID") or str(uuid4())


def _validate_browser_origin(request: Request, *, required: bool) -> None:
    origin = request.headers.get("Origin")
    allowed = get_settings().web_origin
    if (required and not origin) or (origin is not None and origin != allowed):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="request origin rejected")


def _user_response(context_user: User) -> AuthUserResponse:
    return AuthUserResponse.model_validate(context_user)


def _set_session_cookies(response: Response, issued: IssuedSession) -> None:
    settings = get_settings()
    response.set_cookie(
        ACCESS_COOKIE,
        issued.access_token,
        max_age=ACCESS_MAX_AGE,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        issued.refresh_token,
        max_age=REFRESH_MAX_AGE,
        path="/api/v1/auth",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.set_cookie(
        CSRF_COOKIE,
        issued.csrf_token,
        max_age=REFRESH_MAX_AGE,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=False,
        samesite="strict",
    )


def _clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        ACCESS_COOKIE,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.delete_cookie(
        REFRESH_COOKIE,
        path="/api/v1/auth",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.delete_cookie(
        CSRF_COOKIE,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=False,
        samesite="strict",
    )


def _raise_auth_error(exc: Exception) -> None:
    if isinstance(exc, CsrfError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf validation failed") from exc
    if isinstance(exc, LoginRateLimited):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="authentication unavailable") from exc
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials or session") from exc


async def _current_context(request: Request, db: AsyncSession) -> AuthContext:
    try:
        return await get_auth_context(db, access_token=request.cookies.get(ACCESS_COOKIE))
    except AuthenticationError as exc:
        _raise_auth_error(exc)
        raise AssertionError("unreachable") from exc


@router.post("/login", response_model=AuthResponse)
async def login_route(payload: LoginRequest, request: Request, response: Response, db: DbSession) -> AuthResponse:
    _validate_browser_origin(request, required=True)
    try:
        issued = await login(
            db,
            username=payload.username,
            password=payload.password,
            request_id=_request_id(request),
        )
    except (AuthenticationError, LoginRateLimited) as exc:
        _raise_auth_error(exc)
        raise AssertionError("unreachable") from exc
    _set_session_cookies(response, issued)
    return AuthResponse(user=_user_response(issued.user))


@router.get("/me", response_model=AuthUserResponse)
async def me_route(request: Request, db: DbSession) -> AuthUserResponse:
    context = await _current_context(request, db)
    return _user_response(context.user)


@router.post("/refresh", response_model=AuthResponse)
async def refresh_route(request: Request, response: Response, db: DbSession) -> AuthResponse:
    _validate_browser_origin(request, required=False)
    try:
        issued = await refresh(
            db,
            refresh_token=request.cookies.get(REFRESH_COOKIE),
            csrf_token=request.headers.get("X-CSRF-Token"),
            request_id=_request_id(request),
        )
    except (AuthenticationError, CsrfError) as exc:
        _raise_auth_error(exc)
        raise AssertionError("unreachable") from exc
    _set_session_cookies(response, issued)
    return AuthResponse(user=_user_response(issued.user))


@router.post("/change-password", response_model=AuthUserResponse)
async def change_password_route(
    payload: ChangePasswordRequest,
    request: Request,
    db: DbSession,
) -> AuthUserResponse:
    _validate_browser_origin(request, required=False)
    context = await _current_context(request, db)
    try:
        user = await change_password(
            db,
            context=context,
            csrf_token=request.headers.get("X-CSRF-Token"),
            new_password=payload.new_password,
            current_password=payload.current_password,
            request_id=_request_id(request),
        )
    except (AuthenticationError, CsrfError) as exc:
        _raise_auth_error(exc)
        raise AssertionError("unreachable") from exc
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return _user_response(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_route(request: Request, response: Response, db: DbSession) -> Response:
    _validate_browser_origin(request, required=False)
    context = await _current_context(request, db)
    try:
        await logout(
            db,
            context=context,
            csrf_token=request.headers.get("X-CSRF-Token"),
            request_id=_request_id(request),
        )
    except (AuthenticationError, CsrfError) as exc:
        _raise_auth_error(exc)
        raise AssertionError("unreachable") from exc
    _clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
