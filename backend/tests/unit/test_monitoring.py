from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from darknetra.errors import PolicyDenied, Validation
from darknetra.monitor.dedupe import content_hash, normalized_url
from darknetra.monitor.scheduler import catch_up_times
from darknetra.monitor.triage import score
from darknetra.monitor.validation import sources_for, validate_item


def test_validators_and_transliterated_variants():
    value, variants = validate_item("KEYWORD", "  SAFED line  ")
    assert value == "safed line"
    assert "ਸਫੇਦ line" in variants and "सफेद line" in variants
    assert validate_item("ALIAS", "@SYNTHETIC_ALIAS")[0] == "synthetic_alias"
    assert (
        validate_item("TELEGRAM_CHANNEL", "https://t.me/synthetic_channel")[0]
        == "synthetic_channel"
    )
    assert validate_item("PGP_FINGERPRINT", "1234 " * 10)[0] == "1234" * 10
    assert validate_item("IMAGE_HASH", "a" * 16)[0] == "a" * 16


@pytest.mark.parametrize(
    "kind,value",
    [
        ("WALLET", "not-a-wallet"),
        ("ONION_DOMAIN", "a" * 56 + ".onion"),
        ("TELEGRAM_CHANNEL", "t.me/+privateInvite"),
        ("PGP_FINGERPRINT", "f" * 39),
        ("IMAGE_HASH", "f" * 15),
        ("KEYWORD", "   "),
    ],
)
def test_invalid_identifiers_rejected(kind, value):
    with pytest.raises(Validation):
        validate_item(kind, value)


def test_scenario_29_dedupe_uses_body_not_rank_or_snippet():
    first = "https://EXAMPLE.invalid/path?utm_source=rank&q=safed#one"
    second = "https://example.invalid/path?q=safed"
    assert normalized_url(first) == normalized_url(second)
    assert content_hash(first, "first snippet", body_hash="same") == content_hash(
        second, "second snippet", body_hash="same"
    )
    assert content_hash(first, "same", body_hash="body1") != content_hash(
        first, "same", body_hash="body2"
    )
    assert content_hash(first, "different", event_id="synthetic-tx") == content_hash(
        second, "snippet", event_id="synthetic-tx"
    )


def test_scenario_30_keyword_diversity_and_news_gate():
    args = dict(
        excerpt="SYNTHETIC safed line",
        variants=["safed line"],
        item_type="KEYWORD",
        source_class="SYNTHETIC",
        novel=True,
    )
    assert not score(**args, families={"a"}).alertable
    assert score(**args, families={"a", "b"}).alertable
    args["excerpt"] = "A news report about safed line"
    assert not score(**args, families={"a", "b"}).alertable


def test_identifier_first_hit_and_no_false_substring_match():
    args = dict(
        excerpt="SYNTHETIC ffffffffffffffff",
        variants=["ffffffffffffffff"],
        item_type="IMAGE_HASH",
        source_class="SYNTHETIC",
        novel=True,
        families={"a"},
    )
    assert score(**args).alertable
    args.update(
        excerpt="unrelated term", item_type="KEYWORD", variants=["related"], families={"a", "b"}
    )
    assert not score(**args).alertable


def test_scenario_32_catch_up_spacing():
    now = datetime.now(UTC)
    items = [
        SimpleNamespace(id=uuid4(), next_run_at=now - timedelta(hours=2)),
        SimpleNamespace(id=uuid4(), next_run_at=now - timedelta(hours=1)),
    ]
    times = catch_up_times(items, now)
    assert times[items[0].id] == now
    assert times[items[1].id] == now + timedelta(seconds=5)


def test_source_policy_allowset():
    case = SimpleNamespace(
        demo=True,
        source_policy={"allowed_source_classes": ["SYNTHETIC", "REPORT"], "tor_enabled": False},
    )
    settings = SimpleNamespace(offline_mode=True)
    assert sources_for("KEYWORD", [], case, settings) == ["evidence"]
    with pytest.raises(PolicyDenied):
        sources_for("KEYWORD", ["web_search"], case, settings)
