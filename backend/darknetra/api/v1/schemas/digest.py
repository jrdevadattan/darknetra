from datetime import datetime
from uuid import UUID

from .alerts import Alert
from .common import FindingRef, Schema


class CaseDigest(Schema):
    case_id: UUID
    since: datetime
    as_of: datetime
    new_evidence: int
    new_monitor_hits: int
    open_alerts: int
    pending_candidates: int
    top_alerts: list[Alert]
    recent_findings: list[FindingRef]
