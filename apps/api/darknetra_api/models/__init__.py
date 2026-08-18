from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.auth_session import AuthSession
from darknetra_api.models.case import Case
from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.custody import CustodyEvent
from darknetra_api.models.evidence import EvidenceArtifact, EvidenceDerivation
from darknetra_api.models.job import Job
from darknetra_api.models.user import User

metadata_models = (
    User,
    AuthSession,
    Case,
    CaseMembership,
    CaseMembershipRole,
    AuditEvent,
    Job,
    EvidenceArtifact,
    EvidenceDerivation,
    CustodyEvent,
)

__all__ = [
    "AuditEvent",
    "AuthSession",
    "Case",
    "CaseMembership",
    "CaseMembershipRole",
    "CustodyEvent",
    "EvidenceArtifact",
    "EvidenceDerivation",
    "Job",
    "User",
    "metadata_models",
]
