from darknetra_api.authz.permissions import Permission
from darknetra_api.models.enums import GlobalRole
from pydantic import BaseModel


class RolePolicyRead(BaseModel):
    role: GlobalRole
    permissions: list[Permission]


class RolePolicyListResponse(BaseModel):
    roles: list[RolePolicyRead]
