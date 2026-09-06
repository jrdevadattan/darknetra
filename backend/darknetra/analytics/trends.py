"""Deduplicated UTC frequency series. No model-generated term or alert facts."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from statistics import mean, pstdev

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from darknetra.analytics.inputs import load_inputs
from darknetra.analytics.models import TrendBucket
from darknetra.analytics.profiles import timestamp_of, value_of
from darknetra.api.v1.schemas import analytics as dto
from darknetra.errors import Validation

TYPES = {
    "SUBSTANCE",
    "SLANG",
    "SLANG_CANDIDATE",
    "VENDOR_ALIAS",
    "BTC_ADDRESS",
    "ETH_ADDRESS",
    "TRON_ADDRESS",
    "CONTACT_HANDLE",
}


def spike(history, count, *, unique_sources, unique_aliases):
    z = (count - mean(history)) / max(pstdev(history), 1.0) if history else 0.0
    return round(z, 6), z >= 3 and count >= 3 and unique_sources + unique_aliases >= 3


async def compute_buckets(session, case_id, window_days=30, persist=True, *, today=None):
    if not 1 <= window_days <= 366:
        raise Validation("window_days must be between one and 366")
    today = today or datetime.now(UTC).date()
    start = today - timedelta(days=window_days + 13)
    evidence, observations = await load_inputs(session, case_id)
    grouped = defaultdict(
        lambda: {"occurrences": set(), "families": set(), "aliases": set(), "sources": set()}
    )
    for obs in observations:
        if obs.type not in TYPES:
            continue
        item = evidence[obs.evidence_id]
        day = timestamp_of(obs, item.captured_at).date()
        if not start <= day <= today:
            continue
        bucket = grouped[obs.type, value_of(obs), day]
        family = item.sha256
        context = obs.meta.get("context_span", {})
        # Duplicate extraction spans and identical captures do not multiply counts.
        occurrence = (
            family,
            context.get("start", obs.span_start),
            context.get("end", obs.span_end),
        )
        bucket["occurrences"].add(occurrence)
        bucket["families"].add(family)
        if subject := obs.meta.get("subject_value"):
            bucket["aliases"].add(subject)
        source = (
            item.meta.get("source_domain")
            or item.meta.get("channel")
            or obs.meta.get("platform")
            or "unknown"
        )
        bucket["sources"].add(f"{item.source_class}:{source}")
    rows = []
    for (kind, subject, day), values in sorted(grouped.items()):
        attrs = dict(
            case_id=case_id,
            subject_type=kind,
            subject=subject,
            day=day,
            count=len(values["occurrences"]),
            unique_evidence_families=len(values["families"]),
            unique_aliases=len(values["aliases"]),
            unique_sources=len(values["sources"]),
            computed_at=datetime.now(UTC),
        )
        rows.append(TrendBucket(**attrs))
        if persist:
            stmt = insert(TrendBucket).values(**attrs)
            await session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["case_id", "subject_type", "subject", "day"],
                    set_={
                        k: v
                        for k, v in attrs.items()
                        if k not in {"case_id", "subject_type", "subject", "day"}
                    },
                )
            )
    return rows


async def candidates(session, case_id, window_days=30, term=None, buckets=None, *, today=None):
    if not 1 <= window_days <= 366:
        raise Validation("window_days must be between one and 366")
    today = today or datetime.now(UTC).date()
    start = today - timedelta(days=window_days - 1)
    if buckets is None:
        buckets = list(
            await session.scalars(
                select(TrendBucket).where(
                    TrendBucket.case_id == case_id,
                    TrendBucket.day >= start - timedelta(days=14),
                    TrendBucket.day <= today,
                )
            )
        )
    grouped = defaultdict(dict)
    for row in buckets:
        if row.case_id == case_id and (term is None or row.subject.casefold() == term.casefold()):
            grouped[row.subject_type, row.subject][row.day] = row
    series, new_terms = [], []
    for (kind, subject), daily in sorted(grouped.items()):
        points, detected = [], False
        for offset in range(window_days):
            day = start + timedelta(days=offset)
            current = daily.get(day)
            count = current.count if current else 0
            aliases, sources = (
                (current.unique_aliases, current.unique_sources) if current else (0, 0)
            )
            history = [
                daily[previous].count if previous in daily else 0
                for previous in (day - timedelta(days=i) for i in range(1, 15))
            ]
            z, is_candidate = spike(history, count, unique_sources=sources, unique_aliases=aliases)
            detected |= is_candidate
            points.append(
                dto.TrendPoint(
                    day=day,
                    count=count,
                    unique_evidence_families=current.unique_evidence_families if current else 0,
                    unique_aliases=aliases,
                    unique_sources=sources,
                    z=z,
                )
            )
        reasons = (
            ["z_score_count_and_diversity_gate_met"]
            if detected
            else ["no_spike_meeting_count_and_diversity_gate"]
        )
        if kind == "SLANG_CANDIDATE":
            reasons.append("semantic_novelty_model_unavailable; deterministic_observations_only")
            if detected:
                new_terms.append(
                    dto.NewTermCandidate(
                        term=subject,
                        frequency=sum(p.count for p in points),
                        diversity=max(p.unique_aliases + p.unique_sources for p in points),
                        score=max(p.z or 0 for p in points),
                    )
                )
        series.append(
            dto.TrendSeries(
                term=subject, type=kind, points=points, candidate=detected, reasons=reasons
            )
        )
    return dto.Trends(window_days=window_days, series=series, new_term_candidates=new_terms)
