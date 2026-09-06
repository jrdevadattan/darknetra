"""Import all persisted models to register metadata."""

from darknetra.agent.models import (
    Message,
    RateCounter,
    ReplayEntry,
    Run,
    RunEvent,
    Thread,
    ToolCall,
)
from darknetra.analytics.models import (
    ActivityCandidate,
    AnalyticRun,
    GraphEdge,
    LedgerAddress,
    LedgerEdge,
    LedgerNode,
    LinkCandidate,
    TrendBucket,
    WalletAssessment,
)
from darknetra.audit.models import AuditEvent
from darknetra.auth.models import ApiToken, Session, User
from darknetra.cases.models import Case, CaseMembership
from darknetra.decisions.models import Decision, Finding
from darknetra.evidence.models import CustodyEvent, Derivative, Evidence, EvidenceCodeCounter
from darknetra.extract.models import CanonicalEntity, ExtractionRun, Observation, TaxonomyTerm
from darknetra.monitor.models import (
    Alert,
    MonitorHit,
    MonitorRun,
    MonitorSeenUrl,
    Watchlist,
    WatchlistItem,
)
from darknetra.policy.models import PolicyDecision
from darknetra.rag.models import Chunk
from darknetra.reports.models import Report
from darknetra.settings.models import Setting
from darknetra.tools.models import ToolRegistry

__all__ = [
    "User",
    "Session",
    "ApiToken",
    "Case",
    "CaseMembership",
    "AuditEvent",
    "Setting",
    "Evidence",
    "CustodyEvent",
    "Derivative",
    "EvidenceCodeCounter",
    "Chunk",
    "TaxonomyTerm",
    "ExtractionRun",
    "CanonicalEntity",
    "Observation",
    "Thread",
    "Run",
    "Message",
    "ToolCall",
    "RunEvent",
    "ReplayEntry",
    "RateCounter",
    "AnalyticRun",
    "LinkCandidate",
    "ActivityCandidate",
    "WalletAssessment",
    "TrendBucket",
    "GraphEdge",
    "LedgerNode",
    "LedgerEdge",
    "LedgerAddress",
    "Decision",
    "Finding",
    "ToolRegistry",
    "PolicyDecision",
    "Watchlist",
    "WatchlistItem",
    "MonitorRun",
    "MonitorHit",
    "MonitorSeenUrl",
    "Alert",
    "Report",
]
