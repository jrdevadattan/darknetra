"""Explainable screening signals; alerts always require analyst review."""

import re
from dataclasses import dataclass, field

from darknetra.monitor.validation import normalize

CONFIG_VERSION = "monitor-triage-v1"
NEWS_CUES = ("news report", "news agency", "news article", "press release", "awareness campaign")


@dataclass(frozen=True)
class TriageResult:
    relevance: float
    alertable: bool
    reasons: list[str]
    diversity: dict = field(default_factory=dict)


def score(
    *,
    excerpt: str,
    variants: list[str],
    item_type: str,
    source_class: str,
    novel: bool,
    families: set[str],
    image_distance: int | None = None,
) -> TriageResult:
    text = normalize(excerpt)
    matched = {
        normalize(v)
        for v in variants
        if v and re.search(r"(?<!\w)" + re.escape(normalize(v)) + r"(?!\w)", text)
    }
    exact = bool(matched) or image_distance is not None and image_distance <= 8
    reasons = ["Exact item variant matched" if exact else "No exact variant matched"]
    value = 0.4 if exact else 0.0
    if len(matched) > 1:
        extra = min(0.4, (len(matched) - 1) * 0.2)
        value += extra
        reasons.append(f"Additional distinct variants: {len(matched) - 1}")
    if novel:
        value += 0.2
        reasons.append("Previously unseen source family")
    value += {"OSINT_DARK": 0.1, "TELEGRAM": 0.1, "OSINT_SURFACE": 0.05, "CHAIN": 0.2}.get(
        source_class, 0
    )
    if item_type == "KEYWORD" and any(cue in text for cue in NEWS_CUES):
        value -= 0.3
        reasons.append("News or awareness context reduces relevance")
    if image_distance is not None:
        reasons.append(f"Perceptual hash Hamming distance: {image_distance}")
    diverse = item_type not in {"KEYWORD", "ALIAS"} or len(families) >= 2
    if not diverse:
        reasons.append("Diversity gate: two distinct source families in 24 hours required")
    relevance = round(min(1.0, max(0.0, value)), 4)
    alertable = exact and relevance >= 0.6 and diverse
    reasons.append("Review candidate; not proof of identity or conduct")
    return TriageResult(
        relevance,
        alertable,
        reasons,
        {"families": sorted(families), "count": len(families), "window_hours": 24},
    )
