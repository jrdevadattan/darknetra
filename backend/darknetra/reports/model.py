"""Build a case snapshot from stored rows, with complete evidence references."""

import json
from collections import Counter
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from darknetra.agent.claim_checker import verify
from darknetra.agent.models import Thread
from darknetra.analytics.models import (
    ActivityCandidate,
    AnalyticRun,
    GraphEdge,
    LinkCandidate,
    WalletAssessment,
)
from darknetra.audit.models import AuditEvent
from darknetra.crypto.fields import FieldCipher
from darknetra.decisions.models import Decision, Finding
from darknetra.errors import Validation
from darknetra.evidence.models import CustodyEvent, Evidence
from darknetra.evidence.service import get_text
from darknetra.extract.models import CanonicalEntity, ExtractionRun, Observation
from darknetra.monitor.models import Alert, MonitorRun, WatchlistItem
from darknetra.reports.narrative import checked_narrative

SECTION_TITLES = {
    "scope": "Scope and authority",
    "executive_summary": "Executive summary",
    "evidence": "Evidence inventory",
    "observations": "Observations",
    "links": "Link candidates and decisions",
    "activity": "Activity candidates",
    "wallets": "Wallet assessments",
    "graph": "Graph snapshot",
    "timeline": "Timeline",
    "monitoring": "Monitoring",
    "findings": "Promoted findings",
    "methods": "Methods and versions",
    "limitations": "Limitations and contradictions",
    "appendix": "Evidence appendix",
}


class Section(BaseModel):
    key: str
    title: str
    rows: list[dict[str, Any]] = Field(default_factory=list)


class ReportModel(BaseModel):
    case_id: str
    case_code: str
    title: str
    report_id: str
    version: int
    generated_at: datetime
    generated_by: str
    synthetic: bool
    sections: list[Section]
    evidence_manifest: list[dict[str, Any]]
    graph: dict[str, Any]
    claims: list[dict[str, Any]]
    dropped: list[str]
    redacted: bool


def validate_options(options):
    if options.sections and set(options.sections) - set(SECTION_TITLES) - {"cover"}:
        raise Validation("Unknown report section", detail={"allowed": list(SECTION_TITLES)})
    if options.window:
        start, end = options.window.from_, options.window.to
        if any(d is not None and d.tzinfo is None for d in [start, end]):
            raise Validation("Report window requires timezone-aware timestamps")
        if start and end and start > end:
            raise Validation("Report window starts after it ends")


def json_value(value):
    return json.loads(json.dumps(value, default=str))


async def build(db, *, case, report, actor, options, settings, narrative_provider=None):
    validate_options(options)
    selected = set(options.sections or SECTION_TITLES)
    cutoff = report.at
    start = options.window.from_ if options.window else None
    end = min(options.window.to, cutoff) if options.window and options.window.to else cutoff
    evidence = list(
        await db.scalars(
            select(Evidence)
            .where(Evidence.case_id == case.id, Evidence.created_at <= cutoff)
            .order_by(Evidence.code)
        )
    )
    by_id = {e.id: e for e in evidence}
    usable = {e.id: e for e in evidence if e.status in {"READY", "PARTIAL"}}
    cited = set()
    dropped, claims = [], []
    section_rows = {key: [] for key in SECTION_TITLES}

    async def rows(model, time_column=None):
        column = time_column if time_column is not None else model.created_at
        query = select(model).where(model.case_id == case.id, column <= end)
        if start:
            query = query.where(column >= start)
        return list(await db.scalars(query.order_by(column, model.id)))

    def refs(ids):
        if any(eid not in usable for eid in ids):
            dropped.append(
                "A store row referenced unavailable or foreign-case evidence and was omitted"
            )
            return None
        cited.update(ids)
        return [by_id[eid].code for eid in sorted(set(ids), key=lambda eid: by_id[eid].code)]

    authority = "[withheld]"
    if not options.redact and case.authority_ref_enc:
        authority = FieldCipher(settings.field_key).decrypt(
            case.authority_ref_enc, "cases:authority_ref"
        )
    section_rows["scope"] = [
        {
            "scope_notes": case.scope_notes,
            "authority_reference": authority,
            "source_policy": case.source_policy,
            "legal_hold": case.legal_hold,
            "case_status": case.status,
            "window": options.window.model_dump(mode="json", by_alias=True)
            if options.window
            else None,
        }
    ]
    observations = await rows(Observation)
    for obs in observations:
        codes = refs([obs.evidence_id])
        if codes is None:
            continue
        section_rows["observations"].append(
            {
                "type": obs.type,
                "raw": obs.raw,
                "normalized": obs.normalized,
                "valid": obs.valid,
                "validator": obs.validator,
                "confidence": obs.confidence,
                "evidence_codes": codes,
                "span": {"start": obs.span_start, "end": obs.span_end, "line": obs.line_no},
            }
        )
    for model, section, fields in [
        (
            LinkCandidate,
            "links",
            [
                "id",
                "score",
                "band",
                "families",
                "features",
                "contradictions",
                "status",
                "version",
                "supersedes_id",
            ],
        ),
        (ActivityCandidate, "activity", ["id", "score", "label", "features", "status", "version"]),
        (
            WalletAssessment,
            "wallets",
            [
                "id",
                "address",
                "chain",
                "gnn",
                "gnn_unavailable_reason",
                "sanctions",
                "live_summary",
                "tags",
                "traceable",
                "version",
            ],
        ),
    ]:
        for row in await rows(model):
            ids = (
                row.evidence_ids
                if model is LinkCandidate
                else [row.evidence_id]
                if model is ActivityCandidate
                else [row.live_summary_evidence_id]
                if row.live_summary_evidence_id
                else []
            )
            codes = refs(ids)
            if codes is not None:
                section_rows[section].append(
                    {
                        **{field: json_value(getattr(row, field)) for field in fields},
                        "evidence_codes": codes,
                        "limitation": "Scores are indicators for review, not proof.",
                    }
                )
    for finding in await rows(Finding, Finding.at):
        if finding.status != "PROMOTED":
            continue
        successor = await db.scalar(
            select(Finding.id).where(
                Finding.case_id == case.id,
                Finding.supersedes_id == finding.id,
                Finding.at <= cutoff,
            )
        )
        if successor:
            continue
        codes = refs(finding.evidence_ids)
        if not codes:
            continue
        checked = [{"text": finding.claim, "kind": finding.kind.lower(), "evidence_codes": codes}]
        await verify(db, case.id, checked)
        if not checked[0]["verified"]:
            dropped.append(checked[0]["reason"] or "Finding could not be verified")
            continue
        claims.extend(checked)
        section_rows["findings"].append(
            {
                "id": str(finding.id),
                "title": finding.title,
                "claim": finding.claim,
                "kind": finding.kind,
                "evidence_codes": codes,
                "method": finding.method,
                "method_version": finding.method_version,
                "version": finding.version,
                "decision_id": str(finding.decision_id) if finding.decision_id else None,
            }
        )
    decisions = await rows(Decision, Decision.at)
    for decision in decisions:
        section_rows["links"].append(
            {
                "record": "human_decision",
                "id": str(decision.id),
                "target_type": decision.target_type,
                "target_id": str(decision.target_id),
                "target_version": decision.target_version,
                "decision": decision.decision,
                "rationale": decision.rationale,
                "decided_by": str(decision.decided_by),
                "at": decision.at.isoformat(),
                "supersedes_id": str(decision.supersedes_id) if decision.supersedes_id else None,
            }
        )
    nodes = await rows(CanonicalEntity)
    edges = await rows(GraphEdge)
    node_ids = {node.id for node in nodes}
    graph_edges = []
    for edge in edges:
        if edge.src_entity_id not in node_ids or edge.dst_entity_id not in node_ids:
            continue
        graph_edges.append(
            {
                "id": str(edge.id),
                "source": str(edge.src_entity_id),
                "target": str(edge.dst_entity_id),
                "type": edge.type,
                "status": edge.status,
                "decision_id": str(edge.decision_id) if edge.decision_id else None,
                "provenance": edge.provenance,
            }
        )
    graph = {
        "nodes": [{"id": str(n.id), "type": n.type, "display": n.display} for n in nodes],
        "edges": graph_edges,
    }
    section_rows["graph"] = [
        {
            "nodes": len(nodes),
            "edges": len(graph_edges),
            "confirmed_relationships": [
                edge for edge in graph_edges if edge["status"] == "CONFIRMED"
            ],
            "attachment": "graph.json",
        }
    ]
    for event in await rows(AuditEvent, AuditEvent.at):
        section_rows["timeline"].append(
            {
                "at": event.at.isoformat(),
                "action": event.action,
                "actor_kind": event.actor_kind,
                "actor_id": str(event.actor_id) if event.actor_id else None,
                "target_type": event.target_type,
                "target_id": str(event.target_id) if event.target_id else None,
                "result_hash": event.result_hash,
            }
        )
    for item in await rows(WatchlistItem):
        section_rows["monitoring"].append(
            {
                "record": "watchlist_item",
                "id": str(item.id),
                "type": item.type,
                "value": item.value,
                "sources": item.sources,
                "active": item.active,
                "last_run_at": json_value(item.last_run_at),
            }
        )
    for run in await rows(MonitorRun):
        section_rows["monitoring"].append(
            {
                "record": "monitor_run",
                "id": str(run.id),
                "item_id": str(run.item_id),
                "status": run.status,
                "new_hits": run.new_hits,
                "sources_run": run.sources_run,
                "errors": run.errors,
            }
        )
    for alert in await rows(Alert, Alert.at):
        codes = refs(alert.evidence_ids)
        if codes is not None:
            section_rows["monitoring"].append(
                {
                    "record": "alert",
                    "id": str(alert.id),
                    "kind": alert.kind,
                    "status": alert.status,
                    "title": alert.title,
                    "summary": alert.summary,
                    "evidence_codes": codes,
                    "diversity": alert.diversity,
                    "config_version": alert.config_version,
                }
            )
    extraction = await rows(ExtractionRun)
    analytics = await rows(AnalyticRun)
    threads = await rows(Thread)
    section_rows["methods"] = [
        {
            "extractor_versions": sorted({r.bundle_version for r in extraction}),
            "analytic_runs": [
                {"kind": r.kind, "version": r.version, "config_digest": r.config_digest}
                for r in analytics
            ],
            "embedding_model": settings.embedding_model,
            "thread_harnesses": sorted({t.harness for t in threads}),
            "narrative": "deterministic store summary; no model used"
            if narrative_provider is None
            else "claim-checked provider summary",
            "synthetic": case.demo,
        }
    ]
    if options.narrative:
        if narrative_provider:
            prose = await narrative_provider(section_rows)
            accepted, rejected = await checked_narrative(db, case.id, prose)
            claims.extend(accepted)
            dropped.extend(rejected)
            section_rows["executive_summary"] = accepted
            for claim in accepted:
                cited.update(e.id for e in evidence if e.code in claim["evidence_codes"])
        else:
            codes = [e.code for e in evidence if e.id in usable][:10]
            if codes:
                summary = {
                    "text": "The listed records are stored case evidence.",
                    "evidence_codes": codes,
                    "kind": "observed",
                }
                await verify(db, case.id, [summary])
                claims.append(summary)
                cited.update(e.id for e in evidence if e.code in codes)
                section_rows["executive_summary"] = [summary]
    inventory = [
        e
        for e in evidence
        if (not start or e.captured_at >= start) and e.captured_at <= end or e.id in cited
    ]
    custody = list(
        await db.scalars(
            select(CustodyEvent)
            .where(CustodyEvent.case_id == case.id, CustodyEvent.at <= cutoff)
            .order_by(CustodyEvent.at)
        )
    )
    custody_counts = Counter(event.evidence_id for event in custody)
    manifest = []
    for e in inventory:
        entry = {
            "id": str(e.id),
            "code": e.code,
            "sha256": e.sha256,
            "size_bytes": e.size_bytes,
            "kind": e.kind,
            "source_class": e.source_class,
            "origin": e.origin,
            "captured_at": e.captured_at.isoformat(),
            "status": e.status,
            "parent_evidence_id": str(e.parent_evidence_id) if e.parent_evidence_id else None,
            "custody_count": custody_counts[e.id],
        }
        manifest.append(entry)
        section_rows["evidence"].append(entry)
        if e.id in cited and options.include_appendix:
            spans = [r for r in section_rows["observations"] if e.code in r["evidence_codes"]]
            excerpt = ""
            if e.id in usable:
                try:
                    original, _ = await get_text(db, case.id, e.id, settings)
                    excerpt = original[:1200]
                except (FileNotFoundError, Validation):
                    dropped.append("Evidence appendix text unavailable; original hash retained")
                except Exception:
                    dropped.append("Evidence appendix text unavailable; original hash retained")
            section_rows["appendix"].append(
                {
                    **entry,
                    "excerpt": excerpt,
                    "cited_spans": [{"span": s["span"], "text": s["raw"]} for s in spans],
                    "custody": [
                        {
                            "action": c.action,
                            "at": c.at.isoformat(),
                            "actor_kind": c.actor_kind,
                            "hash_verified": c.hash_verified,
                            "note": c.note,
                        }
                        for c in custody
                        if c.evidence_id == e.id
                    ],
                }
            )
    section_rows["limitations"] = [
        {
            "statement": "Scores and automated matches are review indicators, not proof of identity or conduct. Only a current human decision supports a confirmed finding.",
            "unavailable_lanes": sorted(
                {
                    error.get("code", "UNAVAILABLE")
                    for row in section_rows["monitoring"]
                    if row.get("record") == "monitor_run"
                    for error in row["errors"].values()
                }
            ),
            "quarantined_evidence": [e.code for e in evidence if e.status == "QUARANTINED"],
            "unverified_dropped": len(dropped),
            "reasons": dropped,
            "source_classes": sorted({e.source_class for e in inventory}),
        }
    ]
    # Cover/limitations always appear; appendix accompanies every cited code when enabled.
    selected.add("limitations")
    if options.include_appendix:
        selected.add("appendix")
    else:
        selected.discard("appendix")
    return ReportModel(
        case_id=str(case.id),
        case_code=case.code,
        title=case.title,
        report_id=str(report.id),
        version=report.version,
        generated_at=cutoff,
        generated_by=actor.display,
        synthetic=case.demo,
        sections=[
            Section(key=k, title=title, rows=json_value(section_rows[k]))
            for k, title in SECTION_TITLES.items()
            if k in selected
        ],
        evidence_manifest=manifest,
        graph=json_value(graph),
        claims=json_value(claims),
        dropped=dropped,
        redacted=options.redact,
    )
