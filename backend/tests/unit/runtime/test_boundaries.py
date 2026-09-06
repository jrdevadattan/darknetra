import importlib.util
from decimal import Decimal
from types import SimpleNamespace

import pytest


def test_runtime_modules_exist():
    assert importlib.util.find_spec("darknetra.agent.claim_checker") is not None
    assert importlib.util.find_spec("darknetra.capture.fetcher") is not None
    assert importlib.util.find_spec("darknetra.tools.registry") is not None


def test_claim_fence_cannot_hide_uncited_prose():
    from darknetra.agent.claim_checker import extract_claims

    prose, claims = extract_claims(
        'Unrelated factual assertion.\n```claims\n[{"text":"Quoted fact", "evidence_codes":["E-0001"],"kind":"observed"}]\n```'
    )
    assert prose == "Unrelated factual assertion."
    assert any(not c.evidence_codes for c in claims)


def test_claim_citation_fallback_preserves_uncited_sentence():
    from darknetra.agent.claim_checker import extract_claims

    _, claims = extract_claims("A quote [E-0001 L2].\nAn unsupported claim.")
    assert len(claims) == 2
    assert claims[0].evidence_codes == ["E-0001"]
    assert claims[1].evidence_codes == []


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://[::1]/",
        "https://user:pass@example.test/",
        "http://localhost/",
        "http://x.onion/",
        "file:///etc/passwd",
        "https://10.2.3.4/",
    ],
)
def test_unsafe_capture_url_denied(url):
    from darknetra.capture.fetcher import validate_url
    from darknetra.tools.contracts import ToolError

    with pytest.raises(ToolError):
        validate_url(url)


def test_budget_decimal():
    from darknetra.agent.budget import charge, remaining

    thread = SimpleNamespace(budget_usd=Decimal("2"), spent_usd=Decimal("0.1"))
    charge(thread, 0.2)
    assert remaining(thread) == Decimal("1.7")


def test_registry_no_human_decision_and_lanes():
    from darknetra.tools.contracts import AgentRole
    from darknetra.tools.registry import REGISTRY, for_role

    assert "record_decision" not in REGISTRY
    assert "search_evidence" in REGISTRY
    assert "web_search" not in {t.name for t in for_role(AgentRole.DARK_SCOUT)}
    for spec in REGISTRY.values():
        assert spec.input_model.model_json_schema()
        assert spec.output_model.model_json_schema()
        if spec.requires_network:
            assert spec.capture
