from enum import StrEnum


class Permission(StrEnum):
    CASE_CREATE = "CASE_CREATE"
    CASE_VIEW = "CASE_VIEW"
    CASE_EDIT = "CASE_EDIT"
    CASE_CLOSE = "CASE_CLOSE"
    CASE_ARCHIVE = "CASE_ARCHIVE"
    CASE_MANAGE_MEMBERS = "CASE_MANAGE_MEMBERS"
    CASE_MANAGE_POLICY = "CASE_MANAGE_POLICY"
    EVIDENCE_UPLOAD = "EVIDENCE_UPLOAD"
    EVIDENCE_VIEW = "EVIDENCE_VIEW"
    EVIDENCE_VIEW_ORIGINAL = "EVIDENCE_VIEW_ORIGINAL"
    EVIDENCE_RELEASE_QUARANTINE = "EVIDENCE_RELEASE_QUARANTINE"
    THREAD_RUN = "THREAD_RUN"
    THREAD_VIEW = "THREAD_VIEW"
    DECIDE = "DECIDE"
    FINDING_EDIT = "FINDING_EDIT"
    WATCHLIST_MANAGE = "WATCHLIST_MANAGE"
    ALERT_VIEW = "ALERT_VIEW"
    ALERT_HANDLE = "ALERT_HANDLE"
    REPORT_GENERATE = "REPORT_GENERATE"
    EXPORT = "EXPORT"
    AUDIT_VIEW_CASE = "AUDIT_VIEW_CASE"
    AUDIT_VIEW_GLOBAL = "AUDIT_VIEW_GLOBAL"
    ADMIN_USERS = "ADMIN_USERS"
    ADMIN_SETTINGS = "ADMIN_SETTINGS"
    ADMIN_TAXONOMY = "ADMIN_TAXONOMY"
    TOOLS_HEALTH = "TOOLS_HEALTH"


P = Permission
READ = frozenset({P.CASE_VIEW, P.EVIDENCE_VIEW, P.THREAD_VIEW, P.ALERT_VIEW})
ANALYST = READ | {
    P.EVIDENCE_UPLOAD,
    P.THREAD_RUN,
    P.WATCHLIST_MANAGE,
    P.ALERT_HANDLE,
    P.REPORT_GENERATE,
    P.DECIDE,
    P.FINDING_EDIT,
    P.EVIDENCE_VIEW_ORIGINAL,
}
LEAD = ANALYST | {
    P.EVIDENCE_RELEASE_QUARANTINE,
    P.EXPORT,
    P.AUDIT_VIEW_CASE,
    P.CASE_EDIT,
    P.CASE_CLOSE,
    P.CASE_MANAGE_MEMBERS,
    P.CASE_MANAGE_POLICY,
}
CASE_PERMISSIONS = {
    "VIEWER": READ,
    "ANALYST": ANALYST,
    "LEAD": LEAD,
    "OWNER": LEAD | {P.CASE_ARCHIVE},
}
TOKEN_SCOPES = {
    "cases:read": READ - {P.ALERT_VIEW},
    "evidence:write": {P.EVIDENCE_UPLOAD},
    "threads:run": {P.THREAD_RUN},
    "alerts:read": {P.ALERT_VIEW},
    "alerts:handle": {P.ALERT_HANDLE},
    "monitor:run": {P.WATCHLIST_MANAGE},
    "reports:generate": {P.REPORT_GENERATE},
}


def permitted(global_role: str | None, case_role: str | None, permission: Permission) -> bool:
    if global_role == "ADMIN":
        return True
    if permission == P.CASE_CREATE:
        return global_role == "INVESTIGATOR"
    role_permissions = CASE_PERMISSIONS.get(case_role or "", frozenset())
    if global_role == "VIEWER":
        role_permissions = role_permissions & READ
    elif global_role != "INVESTIGATOR":
        return False
    return permission in role_permissions


def scope_permits(scopes: frozenset[str], permission: Permission) -> bool:
    return any(permission in TOKEN_SCOPES.get(scope, set()) for scope in scopes)
