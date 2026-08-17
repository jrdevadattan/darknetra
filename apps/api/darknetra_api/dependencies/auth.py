from collections.abc import Callable, Coroutine
from typing import Annotated, Any
from uuid import UUID

from darknetra_api.authz.permissions import Permission
from darknetra_api.authz.policy import (
    AuthorizationDenied,
    CaseNotFound,
    PasswordChangeRequired,
    authorize_case,
    authorize_global,
)
from darknetra_api.db.session import get_db_session
from darknetra_api.models.case import Case
from darknetra_api.models.user import User
from darknetra_api.services.auth import AuthContext, AuthenticationError, get_auth_context
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

ACCESS_COOKIE = "darknetra_access"
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_auth_context(request: Request, db: DbSession) -> AuthContext:
    try:
        return await get_auth_context(db, access_token=request.cookies.get(ACCESS_COOKIE))
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials or session",
        ) from exc


async def get_current_user(
    context: Annotated[AuthContext, Depends(get_current_auth_context)],
) -> User:
    return context.user


CurrentUser = Annotated[User, Depends(get_current_user)]
GlobalPermissionDependency = Callable[[CurrentUser], Coroutine[Any, Any, User]]
CasePermissionDependency = Callable[[UUID, CurrentUser, DbSession], Coroutine[Any, Any, Case]]


def _raise_authorization_http_error(exc: AuthorizationDenied) -> None:
    if isinstance(exc, PasswordChangeRequired):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="password change required",
        ) from exc
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied") from exc


def require_global_permission(permission: Permission) -> GlobalPermissionDependency:
    async def dependency(user: CurrentUser) -> User:
        try:
            authorize_global(user, permission)
        except AuthorizationDenied as exc:
            _raise_authorization_http_error(exc)
        return user

    return dependency


def require_case_permission(permission: Permission) -> CasePermissionDependency:
    async def dependency(case_id: UUID, user: CurrentUser, db: DbSession) -> Case:
        try:
            await authorize_case(user, case_id, permission, db)
        except CaseNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="resource not found",
            ) from exc
        except AuthorizationDenied as exc:
            _raise_authorization_http_error(exc)

        case = await db.get(Case, case_id)
        if case is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="resource not found",
            )
        return case

    return dependency
