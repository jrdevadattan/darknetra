from typing import Annotated
from uuid import UUID, uuid4

from darknetra_api.authz.policy import AuthorizationDenied, CaseNotFound, PasswordChangeRequired
from darknetra_api.dependencies.auth import CurrentUser, DbSession, get_current_auth_context
from darknetra_api.repositories.memberships import MembershipRecord
from darknetra_api.schemas.memberships import (
    MembershipCreateRequest,
    MembershipListResponse,
    MembershipResponse,
    MembershipUpdateRequest,
)
from darknetra_api.security.csrf import verify_csrf_token
from darknetra_api.services.auth import AuthContext
from darknetra_api.services.memberships import (
    MembershipConflict,
    MembershipNotFound,
    add_case_member,
    list_case_members,
    remove_case_member,
    update_case_member,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

router = APIRouter(prefix="/cases/{case_id}/members", tags=["case-memberships"])


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-ID") or str(uuid4())


def _require_csrf(request: Request, context: AuthContext) -> None:
    token = request.headers.get("X-CSRF-Token")
    if not token or not verify_csrf_token(token, context.auth_session.csrf_token_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf validation failed")


def _membership_response(record: MembershipRecord) -> MembershipResponse:
    return MembershipResponse(
        user_id=record.user.id,
        username=record.user.username,
        display_name=record.user.display_name,
        roles=sorted(record.roles, key=lambda role: role.value),
        created_at=record.membership.created_at,
    )


def _raise_membership_error(exc: Exception) -> None:
    if isinstance(exc, CaseNotFound):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resource not found") from exc
    if isinstance(exc, MembershipNotFound):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resource not found") from exc
    if isinstance(exc, PasswordChangeRequired):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="password change required",
        ) from exc
    if isinstance(exc, AuthorizationDenied):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied") from exc
    if isinstance(exc, MembershipConflict):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    raise exc


@router.get("", response_model=MembershipListResponse)
async def list_case_members_route(
    case_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> MembershipListResponse:
    try:
        records = await list_case_members(db, actor=user, case_id=case_id)
    except AuthorizationDenied as exc:
        _raise_membership_error(exc)
        raise AssertionError("unreachable") from exc
    return MembershipListResponse(items=[_membership_response(record) for record in records])


@router.post("", response_model=MembershipResponse, status_code=status.HTTP_201_CREATED)
async def add_case_member_route(
    case_id: UUID,
    payload: MembershipCreateRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_current_auth_context)],
    db: DbSession,
) -> MembershipResponse:
    _require_csrf(request, context)
    try:
        record = await add_case_member(
            db,
            actor=context.user,
            case_id=case_id,
            target_user_id=payload.user_id,
            roles=payload.roles,
            request_id=_request_id(request),
        )
    except (AuthorizationDenied, MembershipConflict, MembershipNotFound) as exc:
        _raise_membership_error(exc)
        raise AssertionError("unreachable") from exc
    return _membership_response(record)


@router.patch("/{user_id}", response_model=MembershipResponse)
async def update_case_member_route(
    case_id: UUID,
    user_id: UUID,
    payload: MembershipUpdateRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_current_auth_context)],
    db: DbSession,
) -> MembershipResponse:
    _require_csrf(request, context)
    try:
        record = await update_case_member(
            db,
            actor=context.user,
            case_id=case_id,
            target_user_id=user_id,
            roles=payload.roles,
            request_id=_request_id(request),
        )
    except (AuthorizationDenied, MembershipConflict, MembershipNotFound) as exc:
        _raise_membership_error(exc)
        raise AssertionError("unreachable") from exc
    return _membership_response(record)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_case_member_route(
    case_id: UUID,
    user_id: UUID,
    request: Request,
    response: Response,
    context: Annotated[AuthContext, Depends(get_current_auth_context)],
    db: DbSession,
) -> Response:
    _require_csrf(request, context)
    try:
        await remove_case_member(
            db,
            actor=context.user,
            case_id=case_id,
            target_user_id=user_id,
            request_id=_request_id(request),
        )
    except (AuthorizationDenied, MembershipConflict, MembershipNotFound) as exc:
        _raise_membership_error(exc)
        raise AssertionError("unreachable") from exc
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
