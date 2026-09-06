"""Deterministic M4 arithmetic and failure paths, using SYNTHETIC identifiers."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest


def profiles():
    from darknetra.analytics.profiles import AliasProfile

    return [AliasProfile(id=uuid4(), value=f"SYNTHETIC_ALIAS_{i}") for i in range(2)]


def test_scenario_14_shared_service_wallet_cannot_link_operators():
    from darknetra.analytics.link_scoring import score

    a, b = profiles()
    evidence = uuid4()
    for p in (a, b):
        p.wallets["SYNTHETIC_WALLET"] = {evidence}
        p.wallet_tags["SYNTHETIC_WALLET"] = "shared_service"
    result = score(a, b, corpus=[a, b])
    wallet = next(f for f in result.features if f.name == "wallet_reuse")
    assert wallet.value == 0 and wallet.explanation == "shared_service"
    assert result.score == 0 and result.band == "WEAK"


def test_score_preserves_evidence_and_independent_families():
    from darknetra.analytics.link_scoring import score

    a, b = profiles()
    for p in (a, b):
        eid = uuid4()
        p.fingerprints["SYNTHETIC_COMPUTED_FP"] = {eid}
        p.contacts["SYNTHETIC_CONTACT"] = {eid}
        p.wallets["SYNTHETIC_WALLET"] = {eid}
        p.image_hashes["ffffffff00000000"] = {eid}
        p.timestamps = [datetime(2026, 9, 1, tzinfo=UTC)]
    result = score(a, b, corpus=[a, b])
    assert result.score == 78  # .25 + .15 + .18 + .15 + .05
    assert result.band == "STRONG"
    assert {"CRYPTOGRAPHIC_IDENTIFIER", "IMAGE", "CONTACT_CRYPTO"} <= set(result.families)
    assert all(f.evidence_ids for f in result.features if f.contribution)


def test_scenario_15_style_and_template_text_do_not_confirm_identity():
    from darknetra.analytics.link_scoring import score

    a, b = profiles()
    text = "SYNTHETIC template shipping terms and catalog notes " * 15
    for p in (a, b):
        p.texts = [(uuid4(), text), (uuid4(), text)]
    c = profiles()[0]
    c.texts = [(uuid4(), text)]
    result = score(a, b, corpus=[a, b, c])
    assert result.band == "WEAK"
    assert next(f for f in result.features if f.name == "stylometry").value == 0
    assert next(f for f in result.features if f.name == "rare_phrase").value == 0


def test_scenario_13_negative_context_suppresses_news():
    from darknetra.analytics.activity import negative_context, score_signals

    penalty, cues = negative_context("SYNTHETIC news: police seized heroin, court reported seizure")
    assert penalty == 0.5 and "police" in cues
    result = score_signals(
        {"SUBSTANCE": 1.0, "QUANTITY": 1.0, "PRICE": 1.0}, "SYNTHETIC news: police seized heroin"
    )
    assert result.score == pytest.approx(0.2)
    assert result.label == "LOW_SIGNAL"
    assert negative_context("SYNTHETIC उपलब्ध पुलिस अदालत")[0] == 0.5


def test_stock_images_are_discounted_and_wallet_alias_counts_suppress():
    from darknetra.analytics.link_scoring import score

    all_profiles = [*profiles(), *profiles()]
    for p in all_profiles:
        p.wallets["SYNTHETIC_ESCROW"] = {uuid4()}
        p.image_hashes["ffffffff00000000"] = {uuid4()}
    result = score(*all_profiles[:2], corpus=all_profiles)
    assert next(f for f in result.features if f.name == "wallet_reuse").value == 0
    assert next(f for f in result.features if f.name == "image_family").value == pytest.approx(0.2)


def test_trend_spike_needs_independent_sources_or_aliases():
    from darknetra.analytics.trends import spike

    assert spike([0] * 14, 4, unique_sources=1, unique_aliases=1) == (4.0, False)
    assert spike([0] * 14, 4, unique_sources=1, unique_aliases=2) == (4.0, True)


def test_sanctions_missing_dataset_is_unknown_not_clean(tmp_path):
    from darknetra.analytics.sanctions import OfacList

    provider = OfacList(tmp_path / "missing.json")
    assert provider.check("SYNTHETIC_WALLET") is None
    assert "unavailable" in provider.unavailable_reason


def test_blocking_is_bounded_without_dropping_strong_key_first():
    from darknetra.analytics.blocking import candidate_pairs

    values = [*profiles(), *profiles(), *profiles()]
    for p in values:
        p.contacts["SYNTHETIC_CONTACT"] = {uuid4()}
    pairs, truncated = candidate_pairs(values, max_pairs=4)
    assert len(pairs) == 4 and truncated
    assert all(a < b for a, b in pairs)


def test_different_computed_keys_in_overlapping_windows_reduce_rank():
    from darknetra.analytics.link_scoring import score

    a, b = profiles()
    for i, p in enumerate((a, b)):
        p.fingerprints[f"SYNTHETIC_KEY_{i}"] = {uuid4()}
        p.contacts["SYNTHETIC_SHARED"] = {uuid4()}
        p.timestamps = [datetime(2026, 9, 1, tzinfo=UTC)]
    result = score(a, b, corpus=[a, b])
    assert result.score == 5  # contact15 + temporal5 - contradiction15
    assert result.contradictions


def test_sanctions_loaded_list_distinguishes_match_from_checked_absence(tmp_path):
    import json

    from darknetra.analytics.sanctions import OfacList

    path = tmp_path / "SYNTHETIC.json"
    path.write_text(
        json.dumps(
            {
                "list_version": "SYNTHETIC-v1",
                "entries": [
                    {
                        "address": "SYNTHETIC_MATCH",
                        "program": "SYNTHETIC",
                        "entity": "SYNTHETIC entity",
                    }
                ],
            }
        )
    )
    provider = OfacList(path)
    assert provider.check("SYNTHETIC_MATCH").sanctioned is True
    absent = provider.check("SYNTHETIC_ABSENT")
    assert absent.sanctioned is False and absent.list_version == "SYNTHETIC-v1"


def test_ledger_rejects_nonfinite_features_and_dangling_edges():
    from darknetra.analytics.ledger import parse_ledger
    from darknetra.errors import Validation

    header = (
        "source_class,node_index,timestep,label," + ",".join(f"f_{i}" for i in range(102)) + "\n"
    )
    row = "SYNTHETIC,0,1,2," + ",".join("0.1" for _ in range(102)) + "\n"
    mapping = b"source_class,address,chain,node_index,tag\n"
    with pytest.raises(Validation):
        parse_ledger((header + row.replace("0.1", "nan", 1)).encode(), b"src,dst\n", mapping)
    with pytest.raises(Validation):
        parse_ledger((header + row).encode(), b"src,dst\n0,99\n", mapping)


async def test_models_cannot_write_human_decisions():
    from types import SimpleNamespace

    from darknetra.auth.actor import Actor
    from darknetra.decisions.service import decide
    from darknetra.errors import Forbidden

    with pytest.raises(Forbidden):
        await decide(
            None,
            case=SimpleNamespace(id=uuid4()),
            actor=Actor("MODEL", uuid4()),
            target_type="LINK",
            target_id=uuid4(),
            decision="ACCEPT",
            rationale="SYNTHETIC model proposal",
        )
