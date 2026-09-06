from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from .common import ActorRef, EvidenceRef, Schema


class ReportWindow(Schema):
    from_: datetime | None = Field(None, alias="from")
    to: datetime | None = None


class ReportRequest(Schema):
    sections: list[str] | None = None
    redact: bool = True
    include_appendix: bool = True
    narrative: bool = True
    window: ReportWindow | None = None


class ClaimCheck(Schema):
    claims: int
    unverified_dropped: int
    dropped: list[str]


class Report(Schema):
    id: UUID
    case_id: UUID
    version: int
    evidence: EvidenceRef | None = None
    sha256: str | None = None
    generated_by: ActorRef
    at: datetime
    includes: dict[str, Any]
    claim_check: ClaimCheck
    redaction: dict[str, Any]
    status: str


class ReportJob(Schema):
    report_id: UUID
    job_id: str
