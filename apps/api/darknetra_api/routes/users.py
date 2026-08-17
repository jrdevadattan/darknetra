from darknetra_api.authz.permissions import Permission
from darknetra_api.dependencies.auth import CurrentUser, DbSession, require_global_permission
from darknetra_api.models.user import User
from darknetra_api.schemas.users import UserListResponse
from fastapi import APIRouter, Depends
from sqlalchemy import select

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserListResponse)
async def list_users_route(
    _: CurrentUser = Depends(require_global_permission(Permission.USER_READ)),
    db: DbSession = None,
) -> UserListResponse:
    users = list(
        (
            await db.scalars(
                select(User).order_by(User.username_normalized.asc(), User.id.asc())
            )
        ).all()
    )
    return UserListResponse(items=users)
