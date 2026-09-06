import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from darknetra.agent.claim_checker import extract_claims, verify
from darknetra.api.v1.schemas.cases import SourcePolicy
from darknetra.api.v1.schemas.threads import Claim
from darknetra.policy.engine import evaluate
from darknetra.tools.contracts import ToolError


@pytest.mark.parametrize(
    "kwargs,code",
    [
        (
            {
                "offline": True,
                "network": True,
                "source_class": "OSINT_SURFACE",
                "tags": frozenset(),
            },
            "NETWORK_REQUIRED",
        ),
        (
            {"offline": False, "network": True, "source_class": "OSINT_DARK", "tags": frozenset()},
            "POLICY_DENIED",
        ),
        (
            {
                "offline": False,
                "network": True,
                "source_class": "OSINT_SURFACE",
                "tags": frozenset({"tor"}),
            },
            "POLICY_DENIED",
        ),
        (
            {
                "offline": False,
                "network": True,
                "source_class": "OSINT_SURFACE",
                "tags": frozenset({"person_lookup"}),
            },
            "POLICY_DENIED",
        ),
        (
            {
                "offline": False,
                "network": True,
                "source_class": "OSINT_SURFACE",
                "tags": frozenset({"telegram"}),
            },
            "POLICY_DENIED",
        ),
    ],
)
def test_policy_denials(kwargs, code):
    with pytest.raises(ToolError) as failure:
        evaluate(SourcePolicy(), **kwargs)
    assert failure.value.code == code


def test_offline_evidence_allowed():
    evaluate(SourcePolicy(), offline=True, network=False, source_class=None, tags=frozenset())


@pytest.mark.asyncio
async def test_unknown_and_quarantined_claims_fail():
    db = AsyncMock()
    db.scalars.return_value.all = MagicMock(
        return_value=[SimpleNamespace(code="E-0001", status="QUARANTINED", id=uuid4())]
    )
    claims = [
        Claim(text="Claim", evidence_codes=["E-0001"], kind="observed", verified=False),
        Claim(text="Other", evidence_codes=["E-9999"], kind="observed", verified=False),
    ]
    result = await verify(db, uuid4(), claims)
    assert not result.ok
    assert result.unverified_count == 2
    assert all(not claim.verified for claim in claims)


@pytest.mark.asyncio
async def test_unrelated_confirmed_finding_not_confirmation():
    db = AsyncMock()
    identifier = uuid4()
    evidence = SimpleNamespace(code="E-0001", status="READY", id=identifier)
    finding = SimpleNamespace(
        claim="A different accepted conclusion", evidence_ids=[identifier], decision_id=uuid4()
    )
    db.scalars.side_effect = [
        SimpleNamespace(all=lambda: [evidence]),
        SimpleNamespace(all=lambda: [finding]),
    ]
    claim = Claim(
        text="Unrelated confirmation", evidence_codes=["E-0001"], kind="confirmed", verified=False
    )
    result = await verify(db, uuid4(), [claim])
    assert not result.ok
    assert "exact claim" in claim.reason


@pytest.mark.asyncio
async def test_matching_confirmed_finding_requires_current_decision():
    db = AsyncMock()
    identifier = uuid4()
    evidence = SimpleNamespace(code="E-0001", status="READY", id=identifier)
    finding = SimpleNamespace(
        claim="Exact accepted conclusion", evidence_ids=[identifier], decision_id=uuid4()
    )
    db.scalars.side_effect = [
        SimpleNamespace(all=lambda: [evidence]),
        SimpleNamespace(all=lambda: [finding]),
    ]
    db.scalar.side_effect = [SimpleNamespace(id=finding.decision_id), None]
    claim = Claim(
        text="Exact accepted conclusion [E-0001]",
        evidence_codes=["E-0001"],
        kind="confirmed",
        verified=False,
    )
    assert (await verify(db, uuid4(), [claim])).ok
    assert claim.verified


def test_valid_fence_claim_not_duplicated():
    text = "Quoted passage [E-0001 L1]"
    _, claims = extract_claims(
        text
        + "\n```claims\n"
        + json.dumps([{"text": text, "kind": "observed", "evidence_codes": ["E-0001"]}])
        + "\n```"
    )
    assert len(claims) == 1


def test_malformed_fence_is_not_verified_as_empty():
    _, claims = extract_claims("```claims\ninvalid\n```")
    assert claims and not claims[0].evidence_codes


@pytest.mark.parametrize(
    "extra", ["", "\nSYNTHETIC unsupported extra.", " SYNTHETIC unsupported extra."]
)
def test_multisentence_declared_quote_covers_only_its_prose(extra):
    quote = "“SYNTHETIC first sentence. Second source sentence. Third source sentence.” [E-0001 L1]"
    text = (
        quote
        + extra
        + "\n```claims\n"
        + json.dumps([{"text": quote, "kind": "observed", "evidence_codes": ["E-0001"]}])
        + "\n```"
    )
    _, claims = extract_claims(text)
    if not extra:
        assert len(claims) == 1
    else:
        assert any(
            "unsupported extra" in claim.text and not claim.evidence_codes for claim in claims
        )
