from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from darknetra_api.authz.permissions import Permission
from darknetra_api.dependencies.auth import DbSession, require_global_permission
from darknetra_api.models.user import User
from darknetra_api.schemas.users import UserListResponse

router = APIRouter(prefix="/users", tags=["users"])
UserReader = Annotated[User, Depends(require_global_permission(Permission.USER_READ))]


@router.get("", response_model=UserListResponse)
async def list_users_route(db: DbSession, _: UserReader) -> UserListResponse:
    users = list(
        (
            await db.scalars(
                select(User).order_by(User.username_normalized.asc(), User.id.asc())
            )
        ).all()
    )
    return UserListResponse(items=users)
