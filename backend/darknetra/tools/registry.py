"""The single tool catalogue. Human decisions are intentionally not model tools."""

from typing import cast

from pydantic import BaseModel

from darknetra.api.v1.schemas import alerts, analytics, reports
from darknetra.api.v1.schemas.search import SearchQuery, SearchResult
from darknetra.capture.gate import CaptureResult
from darknetra.tools.contracts import AgentRole as R
from darknetra.tools.contracts import Lane, ToolSpec
from darknetra.tools.impl import agent_reach as reach
from darknetra.tools.impl import analytics as a
from darknetra.tools.impl import case as c
from darknetra.tools.impl import delegation as delegation
from darknetra.tools.impl import evidence as e
from darknetra.tools.impl import research as research
from darknetra.tools.impl import robin as robin
from darknetra.tools.impl import surface as s

REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> None:
    if spec.name in REGISTRY:
        raise ValueError("Duplicate tool name")
    if spec.name == "record_decision":
        raise ValueError("Human decisions cannot be registered as model tools")
    REGISTRY[spec.name] = spec


def get(name: str) -> ToolSpec:
    return REGISTRY[name]


def for_role(role: R) -> list[ToolSpec]:
    return [spec for spec in REGISTRY.values() if role in spec.allowed_for]


register(
    ToolSpec(
        name="delegate_task",
        description="Delegate a bounded task to one specialist when useful. The worker inherits case policy and returns citation-checked evidence results. Workers cannot delegate further.",
        input_model=delegation.DelegateTaskInput,
        output_model=delegation.DelegateTaskOutput,
        impl=delegation.delegate_task,
        lane=Lane.CASE,
        allowed_for=frozenset({R.CASE_LEAD}),
        timeout_s=300,
    )
)


EVIDENCE_ROLES = frozenset(
    {R.CASE_LEAD, R.EVIDENCE_ANALYST, R.REPORTER, R.CHAIN_ANALYST, R.IDENTITY_SCOUT}
)
for name, inp, out, impl, description in [
    (
        "search_evidence",
        SearchQuery,
        SearchResult,
        e.search_evidence,
        "Search captured case evidence; returns excerpts with evidence codes and spans.",
    ),
    (
        "read_evidence",
        e.ReadInput,
        e.ReadOutput,
        e.read_evidence,
        "Read bounded line-numbered TEXT from case evidence; never reads quarantined originals.",
    ),
    (
        "list_entities",
        e.EntityInput,
        e.EntitiesOutput,
        e.list_entities,
        "List deterministic observed entities and their evidence codes; entities are not confirmed identities.",
    ),
    (
        "extract_indicators",
        e.ExtractInput,
        e.ExtractOutput,
        e.extract_indicators,
        "Run deterministic extraction on stored evidence; creates observations, never confirmed findings.",
    ),
    (
        "transcribe_image",
        e.ImageInput,
        e.ImageOutput,
        e.transcribe_image,
        "Transcribe a stored image only if a configured OCR provider is available.",
    ),
]:
    register(
        ToolSpec(
            name=name,
            description=description,
            input_model=cast(type[BaseModel], inp),
            output_model=cast(type[BaseModel], out),
            lane=Lane.EVIDENCE,
            impl=impl,
            allowed_for=EVIDENCE_ROLES,
            unavailable_reason="OCR provider is not configured"
            if name == "transcribe_image"
            else None,
        )
    )


for name, inp, out, impl, lane, roles, description in [
    (
        "correlate_entities",
        analytics.CorrelateRequest,
        a.CorrelationOutput,
        a.correlate_entities,
        Lane.ANALYTICS,
        frozenset({R.CASE_LEAD, R.EVIDENCE_ANALYST}),
        "Compute evidence-backed link candidates deterministically; scores never confirm identity.",
    ),
    (
        "graph",
        a.GraphInput,
        a.GraphOutput,
        a.graph,
        Lane.ANALYTICS,
        EVIDENCE_ROLES,
        "Read the case graph and its evidence references; pending edges remain candidates.",
    ),
    (
        "assess_wallet",
        analytics.WalletAssessRequest,
        a.WalletOutput,
        a.assess_wallet,
        Lane.ANALYTICS,
        frozenset({R.CASE_LEAD, R.CHAIN_ANALYST}),
        "Assess a validated address using available local models and lists; unavailable checks remain explicitly unknown.",
    ),
    (
        "detect_trends",
        a.TrendInput,
        a.TrendOutput,
        a.detect_trends,
        Lane.ANALYTICS,
        frozenset({R.CASE_LEAD, R.EVIDENCE_ANALYST}),
        "Read deterministic case term counts and diversity gates with source references; no semantic model claims.",
    ),
    (
        "list_alerts",
        c.AlertInput,
        c.AlertOutput,
        c.list_alerts,
        Lane.CASE,
        EVIDENCE_ROLES,
        "Read case alerts with evidence references; never acknowledge or decide an alert.",
    ),
    (
        "changes_since",
        c.ChangesInput,
        alerts.Changes,
        c.changes_since,
        Lane.CASE,
        EVIDENCE_ROLES,
        "Read persisted case changes since a timezone-qualified timestamp.",
    ),
    (
        "build_investigation_pack",
        reports.ReportRequest,
        reports.Report,
        c.build_investigation_pack,
        Lane.CASE,
        frozenset({R.CASE_LEAD, R.REPORTER}),
        "Generate a versioned investigation pack from persisted case records with claim checks and role-authorized redaction.",
    ),
]:
    register(
        ToolSpec(
            name=name,
            description=description,
            input_model=cast(type[BaseModel], inp),
            output_model=cast(type[BaseModel], out),
            impl=impl,
            lane=lane,
            allowed_for=roles,
            timeout_s=120,
        )
    )

for name, inp, impl, lane, source, role, tags, reason in [
    (
        "web_search",
        s.QueryInput,
        s.web_search,
        Lane.SURFACE,
        "OSINT_SURFACE",
        R.SURFACE_SCOUT,
        frozenset(),
        None,
    ),
    (
        "fetch_page",
        s.UrlInput,
        s.fetch_page,
        Lane.SURFACE,
        "OSINT_SURFACE",
        R.SURFACE_SCOUT,
        frozenset(),
        None,
    ),
    (
        "wayback_lookup",
        s.UrlInput,
        s.wayback_lookup,
        Lane.SURFACE,
        "OSINT_SURFACE",
        R.SURFACE_SCOUT,
        frozenset(),
        None,
    ),
    (
        "onion_search",
        s.QueryInput,
        s.onion_search,
        Lane.DARK,
        "OSINT_DARK",
        R.DARK_SCOUT,
        frozenset(),
        None,
    ),
    (
        "onion_lookup",
        s.UrlInput,
        s.unavailable,
        Lane.DARK,
        "OSINT_DARK",
        R.DARK_SCOUT,
        frozenset(),
        "Index adapter unavailable",
    ),
    (
        "onion_fetch",
        s.UrlInput,
        s.unavailable,
        Lane.DARK,
        "OSINT_DARK",
        R.DARK_SCOUT,
        frozenset({"tor"}),
        "Isolated M9 collector is not installed",
    ),
    (
        "keyserver_lookup",
        s.KeyInput,
        s.keyserver_lookup,
        Lane.IDENTITY,
        "OSINT_SURFACE",
        R.IDENTITY_SCOUT,
        frozenset(),
        None,
    ),
    (
        "username_lookup",
        s.QueryInput,
        s.unavailable,
        Lane.IDENTITY,
        "OSINT_SURFACE",
        R.IDENTITY_SCOUT,
        frozenset({"person_lookup"}),
        "Observation-bound identity gateway unavailable",
    ),
    (
        "chain_lookup",
        s.ChainInput,
        s.chain_lookup,
        Lane.CHAIN,
        "CHAIN",
        R.CHAIN_ANALYST,
        frozenset(),
        None,
    ),
    (
        "sanctions_check",
        s.ChainInput,
        s.unavailable,
        Lane.CHAIN,
        "CHAIN",
        R.CHAIN_ANALYST,
        frozenset(),
        "No verified sanctions dataset or compliant live adapter",
    ),
    (
        "telegram_channel_read",
        s.QueryInput,
        s.unavailable,
        Lane.TELEGRAM,
        "TELEGRAM",
        R.SURFACE_SCOUT,
        frozenset({"telegram"}),
        "Apify POST is prohibited by GET/HEAD invariant",
    ),
]:
    register(
        ToolSpec(
            name=name,
            description=f"{name}: read-only public lookup captured as immutable evidence before returning a bounded excerpt. Failure is explicit; absence is not a clean result.",
            input_model=cast(type[BaseModel], inp),
            output_model=CaptureResult,
            lane=lane,
            impl=impl,
            allowed_for=frozenset({R.CASE_LEAD, role}),
            requires_network=True,
            source_class=source,
            policy_tags=tags,
            rate_key=lane.value.lower(),
            capture=True,
            unavailable_reason=reason,
        )
    )

for name, inp, out, impl, lane, source, role, description in [
    (
        "public_page_read",
        research.PublicPageInput,
        research.PublicPageOutput,
        research.public_page_read,
        Lane.SURFACE,
        "OSINT_SURFACE",
        R.SURFACE_SCOUT,
        "Capture a public HTML page, then extract bounded main text with Trafilatura. Every excerpt cites the captured page.",
    ),
    (
        "agent_reach_read",
        reach.ReaderInput,
        reach.ReaderOutput,
        reach.agent_reach_read,
        Lane.SURFACE,
        "OSINT_SURFACE",
        R.SURFACE_SCOUT,
        "Agent Reach public-web channel through captured Jina Reader. Discloses requested URL to Jina; output is an intermediary representation, not verified origin content.",
    ),
    (
        "robin_search",
        robin.RobinSearchInput,
        robin.RobinSearchOutput,
        robin.robin_search,
        Lane.DARK,
        "OSINT_DARK",
        R.DARK_SCOUT,
        "Parse a captured public Ahmia index using attributed Robin code; returns cited index observations and never fetches listed targets.",
    ),
    (
        "surface_search",
        research.SurfaceSearchInput,
        research.SurfaceSearchOutput,
        research.surface_search,
        Lane.SURFACE,
        "OSINT_SURFACE",
        R.SURFACE_SCOUT,
        "Search public web with DuckDuckGo or configured SearXNG; returns bounded captured SERP observations, not verified target-page content.",
    ),
    (
        "rss_read",
        research.RssReadInput,
        research.RssReadOutput,
        research.rss_read,
        Lane.SURFACE,
        "OSINT_SURFACE",
        R.SURFACE_SCOUT,
        "Read a public RSS/Atom feed through capture and feedparser; returns cited entries without fetching linked pages.",
    ),
]:
    register(
        ToolSpec(
            name=name,
            description=description,
            input_model=cast(type[BaseModel], inp),
            output_model=cast(type[BaseModel], out),
            impl=impl,
            lane=lane,
            source_class=source,
            allowed_for=frozenset({R.CASE_LEAD, role}),
            requires_network=True,
            capture=True,
            rate_key=lane.value.lower(),
        )
    )
