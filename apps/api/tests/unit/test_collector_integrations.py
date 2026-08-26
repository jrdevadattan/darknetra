from __future__ import annotations

import json

import pytest

from services.collector.darknetra_collector.adapters import (
    get_integration_catalog,
    normalize_integration_output,
)
from services.collector.darknetra_collector.policy import (
    CollectionRequest,
    CollectorPolicy,
    PolicyViolation,
)


def onion_url(character: str = "a") -> str:
    return f"http://{character * 56}.onion/research"


def test_catalog_covers_every_requested_project_with_an_explicit_pipeline_role() -> None:
    catalog = get_integration_catalog()

    assert {item.slug for item in catalog} == {
        "dark-web-analysis",
        "dark-web-links",
        "github-osint-tools",
        "navigating-darkweb-hunting",
        "networkchuck-scraping-guide",
        "robin",
        "torbot",
    }
    assert all(item.repository_url.startswith("https://") for item in catalog)
    assert all(item.pipeline_role for item in catalog)
    assert all(item.integration_mode in {"IMPORT", "REFERENCE", "DISCOVERY"} for item in catalog)


def test_robin_markdown_is_normalized_into_provenanced_observations() -> None:
    report = """# Investigation\n\n## Findings\n- Alias: northlane_vendor\n- Wallet: bc1qexamplewallet\n- Source: http://exampleexampleexampleexampleexampleexampleexampleexample.onion/post/7\n"""

    result = normalize_integration_output(
        adapter="robin",
        payload=report.encode(),
        source_name="Robin investigation package",
    )

    assert result.adapter == "robin"
    assert (
        result.content_sha256 == "3a657287e7ee5f24d23570403c0dbf105797446b0d6b43fc91743d46f8b98a27"
    )
    assert result.observations[0].kind == "REPORT"
    assert "northlane_vendor" in result.observations[0].value
    assert result.observations[0].provenance == "Robin investigation package"


def test_torbot_json_tree_is_flattened_without_losing_parent_relationships() -> None:
    payload = json.dumps(
        {
            "url": onion_url("b"),
            "title": "Root forum",
            "children": [
                {"url": onion_url("c"), "title": "Thread 14", "children": []},
            ],
        }
    ).encode()

    result = normalize_integration_output(
        adapter="torbot",
        payload=payload,
        source_name="TorBot bounded crawl",
    )

    assert [(item.kind, item.value) for item in result.observations] == [
        ("PAGE", onion_url("b")),
        ("LINK", onion_url("c")),
    ]
    assert result.observations[1].parent == onion_url("b")


def test_collector_policy_accepts_only_bounded_read_only_onion_requests() -> None:
    validated = CollectorPolicy().validate(
        CollectionRequest(url=onion_url(), method="GET", depth=1, pages_so_far=3, bytes_so_far=1024)
    )

    assert validated.url == onion_url()
    assert validated.method == "GET"


@pytest.mark.parametrize(
    ("collection_request", "code"),
    [
        (CollectionRequest(url="https://example.com", method="GET"), "HOST_NOT_ALLOWED"),
        (CollectionRequest(url=onion_url(), method="POST"), "METHOD_NOT_ALLOWED"),
        (CollectionRequest(url=onion_url(), method="GET", depth=2), "DEPTH_LIMIT"),
        (CollectionRequest(url=onion_url(), method="GET", pages_so_far=25), "PAGE_LIMIT"),
        (
            CollectionRequest(url=f"http://user:pass@{'a' * 56}.onion", method="GET"),
            "CREDENTIALS_NOT_ALLOWED",
        ),
        (
            CollectionRequest(url=f"http://{'a' * 56}.onion/file.exe", method="GET"),
            "EXTENSION_BLOCKED",
        ),
    ],
)
def test_collector_policy_rejects_unsafe_or_unbounded_requests(
    collection_request: CollectionRequest,
    code: str,
) -> None:
    with pytest.raises(PolicyViolation) as caught:
        CollectorPolicy().validate(collection_request)

    assert caught.value.code == code
