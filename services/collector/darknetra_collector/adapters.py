from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

IntegrationMode = Literal["IMPORT", "REFERENCE", "DISCOVERY"]


@dataclass(frozen=True)
class IntegrationDefinition:
    slug: str
    name: str
    repository_url: str
    integration_mode: IntegrationMode
    pipeline_role: str
    accepted_outputs: tuple[str, ...] = ()


@dataclass(frozen=True)
class NormalizedObservation:
    kind: str
    value: str
    provenance: str
    title: str | None = None
    parent: str | None = None


@dataclass(frozen=True)
class NormalizedPackage:
    adapter: str
    content_sha256: str
    observations: tuple[NormalizedObservation, ...]


_CATALOG = (
    IntegrationDefinition(
        slug="robin",
        name="Robin",
        repository_url="https://github.com/apurvsinghgautam/robin",
        integration_mode="IMPORT",
        pipeline_role="Import grounded investigation reports and reviewed search results into evidence processing.",
        accepted_outputs=("report", "markdown"),
    ),
    IntegrationDefinition(
        slug="torbot",
        name="TorBot",
        repository_url="https://github.com/DedSecInside/TorBot",
        integration_mode="IMPORT",
        pipeline_role="Normalize bounded JSON link trees into page and relationship observations.",
        accepted_outputs=("json-link-tree",),
    ),
    IntegrationDefinition(
        slug="dark-web-analysis",
        name="Dark-Web-analysis",
        repository_url="https://github.com/Jash-2000/Dark-Web-analysis",
        integration_mode="IMPORT",
        pipeline_role="Map research crawl datasets into the common observation and correlation schema.",
        accepted_outputs=("json-dataset", "csv-dataset"),
    ),
    IntegrationDefinition(
        slug="github-osint-tools",
        name="GitHub OSINT Tools",
        repository_url="https://github.com/topics/osint-tools",
        integration_mode="DISCOVERY",
        pipeline_role="Curate candidate tooling for administrator review; never auto-install repositories.",
    ),
    IntegrationDefinition(
        slug="networkchuck-scraping-guide",
        name="Dark Web Scraping Guide",
        repository_url="https://github.com/theNetworkChuck/dark-web-scraping-guide",
        integration_mode="REFERENCE",
        pipeline_role="Operational reference for isolated Robin deployment and investigator safety controls.",
    ),
    IntegrationDefinition(
        slug="dark-web-links",
        name="Dark-Web-Links",
        repository_url="https://github.com/MTXPr0ject/Dark-Web-Links",
        integration_mode="DISCOVERY",
        pipeline_role="Supply candidate sources to the approval queue without automatically visiting them.",
    ),
    IntegrationDefinition(
        slug="navigating-darkweb-hunting",
        name="Intelligence and Hunting Methodology",
        repository_url="https://navigating-the-darkweb.readthedocs.io/en/latest/chapter7_intelligence_and_hunting_on_the_darkweb.html",
        integration_mode="REFERENCE",
        pipeline_role="Define the source, collection, extraction, preservation, and reporting workflow.",
    ),
)


def get_integration_catalog() -> tuple[IntegrationDefinition, ...]:
    return _CATALOG


def normalize_integration_output(
    *,
    adapter: str,
    payload: bytes,
    source_name: str,
) -> NormalizedPackage:
    digest = hashlib.sha256(payload).hexdigest()
    if adapter == "robin":
        text = payload.decode("utf-8")
        observations = (
            NormalizedObservation(
                kind="REPORT",
                value=text,
                provenance=source_name,
                title=_first_heading(text),
            ),
        )
    elif adapter == "torbot":
        decoded = json.loads(payload)
        if not isinstance(decoded, dict):
            raise ValueError("TorBot output must be a JSON object")
        observations = tuple(_flatten_torbot(decoded, source_name=source_name, parent=None))
    else:
        raise ValueError(f"adapter {adapter!r} does not support direct normalization")
    return NormalizedPackage(adapter=adapter, content_sha256=digest, observations=observations)


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or None
    return None


def _flatten_torbot(
    node: dict[str, Any],
    *,
    source_name: str,
    parent: str | None,
) -> list[NormalizedObservation]:
    url = node.get("url")
    if not isinstance(url, str) or not url:
        raise ValueError("TorBot nodes require a URL")
    title = node.get("title") if isinstance(node.get("title"), str) else None
    observations = [
        NormalizedObservation(
            kind="PAGE" if parent is None else "LINK",
            value=url,
            provenance=source_name,
            title=title,
            parent=parent,
        )
    ]
    children = node.get("children", [])
    if not isinstance(children, list):
        raise TypeError("TorBot children must be a list")
    for child in children:
        if not isinstance(child, dict):
            raise TypeError("TorBot children must be objects")
        observations.extend(_flatten_torbot(child, source_name=source_name, parent=url))
    return observations


__all__ = [
    "IntegrationDefinition",
    "NormalizedObservation",
    "NormalizedPackage",
    "get_integration_catalog",
    "normalize_integration_output",
]
