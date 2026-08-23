from datetime import datetime
from uuid import UUID

from darknetra_api.models.enums import CaseSensitivity, CaseStatus
from pydantic import BaseModel, ConfigDict, Field, model_validator

CASE_CODE_PATTERN = r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$"


class CaseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    case_code: str = Field(min_length=3, max_length=40, pattern=CASE_CODE_PATTERN)
    title: str = Field(min_length=3, max_length=200)
    sensitivity: CaseSensitivity
    source_authority_summary: str = Field(min_length=1, max_length=500)


class CaseUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=3, max_length=200)
    sensitivity: CaseSensitivity | None = None
    source_authority_summary: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def require_change(self) -> "CaseUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one case field must be supplied")
        return self


class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_code: str
    title: str
    status: CaseStatus
    sensitivity: CaseSensitivity
    owner_user_id: UUID
    source_authority_summary: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class CaseListResponse(BaseModel):
    items: list[CaseResponse]
    limit: int
    offset: int
    has_more: bool
