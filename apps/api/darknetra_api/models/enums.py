from enum import StrEnum


class GlobalRole(StrEnum):
    ADMIN = "ADMIN"
    CASE_OWNER = "CASE_OWNER"
    COLLECTOR = "COLLECTOR"
    ANALYST = "ANALYST"
    REVIEWER = "REVIEWER"
    AUDITOR = "AUDITOR"
    VIEWER = "VIEWER"


class CaseStatus(StrEnum):
    OPEN = "OPEN"
    REVIEW = "REVIEW"
    CLOSED = "CLOSED"


class CaseSensitivity(StrEnum):
    STANDARD = "STANDARD"
    RESTRICTED = "RESTRICTED"
