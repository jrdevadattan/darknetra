from typing import Annotated
from uuid import UUID, uuid4

from darknetra_api.authz.permissions import Permission
from darknetra_api.authz.policy import AuthorizationDenied, CaseNotFound, PasswordChangeRequired
from darknetra_api.dependencies.auth import (
    CurrentUser,
    DbSession,
    get_current_auth_context,
    require_case_permission,
)
from darknetra_api.models.case import Case
from darknetra_api.repositories.cases import list_visible_cases
from darknetra_api.schemas.cases import (
    CaseCreateRequest,
    CaseListResponse,
    CaseResponse,
    CaseUpdateRequest,
)
from darknetra_api.security.csrf import verify_csrf_token
from darknetra_api.services.auth import AuthContext
from darknetra_api.services.cases import (
    CaseLifecycleConflict,
    close_case,
    create_case,
    reopen_case,
    update_case,
)
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

router = APIRouter(prefix="/cases", tags=["cases"])


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-ID") or str(uuid4())


def _require_csrf(request: Request, context: AuthContext) -> None:
    token = request.headers.get("X-CSRF-Token")
    if not token or not verify_csrf_token(token, context.auth_session.csrf_token_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf validation failed")


def _raise_case_error(exc: Exception) -> None:
    if isinstance(exc, CaseNotFound):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resource not found") from exc
    if isinstance(exc, PasswordChangeRequired):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="password change required",
        ) from exc
    if isinstance(exc, AuthorizationDenied):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied") from exc
    if isinstance(exc, CaseLifecycleConflict):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    raise exc


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case_route(
    payload: CaseCreateRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_current_auth_context)],
    db: DbSession,
) -> Case:
    _require_csrf(request, context)
    try:
        return await create_case(
            db,
            actor=context.user,
            payload=payload,
            request_id=_request_id(request),
        )
    except (AuthorizationDenied, CaseLifecycleConflict) as exc:
        _raise_case_error(exc)
        raise AssertionError("unreachable") from exc


@router.get("", response_model=CaseListResponse)
async def list_cases_route(
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CaseListResponse:
    items, has_more = await list_visible_cases(db, user=user, limit=limit, offset=offset)
    return CaseListResponse(items=items, limit=limit, offset=offset, has_more=has_more)


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case_route(
    case: Annotated[Case, Depends(require_case_permission(Permission.CASE_READ))],
) -> Case:
    return case


@router.patch("/{case_id}", response_model=CaseResponse)
async def update_case_route(
    case_id: UUID,
    payload: CaseUpdateRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_current_auth_context)],
    db: DbSession,
) -> Case:
    _require_csrf(request, context)
    try:
        return await update_case(
            db,
            actor=context.user,
            case_id=case_id,
            payload=payload,
            request_id=_request_id(request),
        )
    except (AuthorizationDenied, CaseLifecycleConflict) as exc:
        _raise_case_error(exc)
        raise AssertionError("unreachable") from exc


@router.post("/{case_id}/close", response_model=CaseResponse)
async def close_case_route(
    case_id: UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(get_current_auth_context)],
    db: DbSession,
) -> Case:
    _require_csrf(request, context)
    try:
        return await close_case(
            db,
            actor=context.user,
            case_id=case_id,
            request_id=_request_id(request),
        )
    except (AuthorizationDenied, CaseLifecycleConflict) as exc:
        _raise_case_error(exc)
        raise AssertionError("unreachable") from exc


@router.post("/{case_id}/reopen", response_model=CaseResponse)
async def reopen_case_route(
    case_id: UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(get_current_auth_context)],
    db: DbSession,
) -> Case:
    _require_csrf(request, context)
    try:
        return await reopen_case(
            db,
            actor=context.user,
            case_id=case_id,
            request_id=_request_id(request),
        )
    except (AuthorizationDenied, CaseLifecycleConflict) as exc:
        _raise_case_error(exc)
        raise AssertionError("unreachable") from exc
