from typing import Annotated

from fastapi import APIRouter, Depends

from darknetra_api.authz.permissions import Permission
from darknetra_api.authz.policy import ROLE_PERMISSIONS
from darknetra_api.dependencies.auth import require_global_permission
from darknetra_api.models.user import User
from darknetra_api.schemas.admin import RolePolicyListResponse, RolePolicyRead

router = APIRouter(prefix="/admin", tags=["administration"])
RoleReader = Annotated[User, Depends(require_global_permission(Permission.ROLE_READ))]


@router.get("/roles", response_model=RolePolicyListResponse)
async def list_role_policies_route(_: RoleReader) -> RolePolicyListResponse:
    roles = [
        RolePolicyRead(
            role=role,
            permissions=sorted(permissions, key=lambda permission: permission.value),
        )
        for role, permissions in sorted(ROLE_PERMISSIONS.items(), key=lambda item: item[0].value)
    ]
    return RolePolicyListResponse(roles=roles)
