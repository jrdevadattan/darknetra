"""SYNTHETIC inputs verify parsers and capture gate invariants for infra tools.

Unit tests cover:
  - parse_onionscan_output: various JSON shapes including partial/missing fields
  - parse_crtsh_response: deduplication, confidence labels, truncation
Integration stubs verify:
  - capture gate is invoked before any parsing
  - quarantined captures suppress parsing
  - gate failures propagate without parsing
  - onion_fingerprint rejects non-onion URLs before capture
  - clearnet_cert_match rejects missing both query terms
"""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from darknetra.capture.fetcher import Fetched
from darknetra.capture.gate import CaptureResult
from darknetra.tools.contracts import ToolError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SYNTHETIC_HOST = "a" * 56 + ".onion"
SYNTHETIC_URL = f"http://{SYNTHETIC_HOST}/synthetic"


def captured_result(*, quarantined: bool = False) -> CaptureResult:
    return CaptureResult(
        evidence_code="E-0099",
        evidence_id=uuid4(),
        duplicate=False,
        excerpt="SYNTHETIC fingerprint captured",
        source_class="OSINT_DARK",
        captured_at=datetime.now(UTC),
        quarantined=quarantined,
    )


# ---------------------------------------------------------------------------
# parse_onionscan_output — unit tests (no DB, no network)
# ---------------------------------------------------------------------------


def test_parse_full_onionscan_report():
    from darknetra.tools.impl.infra import parse_onionscan_output

    payload = {
        "hiddenService": SYNTHETIC_HOST,
        "online": True,
        "certificate": {
            "commonName": "SYNTHETIC clearnet domain",
            "dnsNames": ["SYNTHETIC clearnet domain", "www.SYNTHETIC clearnet domain"],
            "serialNumber": "AABBCCDD1122",
            "issuer": "SYNTHETIC CA",
        },
        "responseHeaders": {
            "Server": "Apache/2.4",
            "X-Powered-By": "PHP/7.4",
        },
        "webdetects": {
            "serverStatus": True,
            "phpInfo": False,
            "openDirectories": False,
            "robotsTxt": False,
        },
        "linkedOnions": [SYNTHETIC_URL, SYNTHETIC_URL + "/second"],
    }
    result = parse_onionscan_output(json.dumps(payload).encode())
    assert result["tls_cert"]["cn"] == "SYNTHETIC clearnet domain"
    assert "SYNTHETIC clearnet domain" in result["tls_cert"]["san"]
    assert result["tls_cert"]["serial"] == "AABBCCDD1122"
    assert result["tls_cert"]["issuer"] == "SYNTHETIC CA"
    assert result["server_header"] == "Apache/2.4"
    assert result["powered_by"] == "PHP/7.4"
    assert SYNTHETIC_URL in result["exposed_paths"]
    assert result["status_page_found"] is True


def test_parse_onionscan_partial_missing_cert():
    from darknetra.tools.impl.infra import parse_onionscan_output

    payload = {"online": True, "responseHeaders": {"server": "nginx"}}
    result = parse_onionscan_output(json.dumps(payload).encode())
    assert result["tls_cert"] is None
    assert result["server_header"] == "nginx"
    assert result["status_page_found"] is False
    assert result["exposed_paths"] == []


def test_parse_onionscan_empty_cert_dict_produces_no_tls_cert():
    from darknetra.tools.impl.infra import parse_onionscan_output

    payload = {"certificate": {}}
    result = parse_onionscan_output(json.dumps(payload).encode())
    assert result["tls_cert"] is None


def test_parse_onionscan_caps_exposed_paths_at_50():
    from darknetra.tools.impl.infra import parse_onionscan_output

    payload = {"linkedOnions": [SYNTHETIC_URL + f"/{i}" for i in range(100)]}
    result = parse_onionscan_output(json.dumps(payload).encode())
    assert len(result["exposed_paths"]) == 50


def test_parse_onionscan_caps_san_at_20():
    from darknetra.tools.impl.infra import parse_onionscan_output

    payload = {
        "certificate": {
            "commonName": "SYNTHETIC",
            "dnsNames": [f"SYNTHETIC-{i}.example.test" for i in range(30)],
        }
    }
    result = parse_onionscan_output(json.dumps(payload).encode())
    assert len(result["tls_cert"]["san"]) == 20


def test_parse_onionscan_non_json_raises_unavailable():
    from darknetra.tools.impl.infra import parse_onionscan_output

    with pytest.raises(ToolError) as exc:
        parse_onionscan_output(b"not-json-SYNTHETIC")
    assert exc.value.code == "UNAVAILABLE"


def test_parse_onionscan_non_dict_json_raises_unavailable():
    from darknetra.tools.impl.infra import parse_onionscan_output

    with pytest.raises(ToolError) as exc:
        parse_onionscan_output(b'["SYNTHETIC","array"]')
    assert exc.value.code == "UNAVAILABLE"


def test_parse_onionscan_status_page_detected_via_phpinfo():
    from darknetra.tools.impl.infra import parse_onionscan_output

    payload = {"webdetects": {"phpInfo": True}}
    result = parse_onionscan_output(json.dumps(payload).encode())
    assert result["status_page_found"] is True


# ---------------------------------------------------------------------------
# parse_crtsh_response — unit tests
# ---------------------------------------------------------------------------


def test_parse_crtsh_serial_match_is_high_confidence():
    from darknetra.tools.impl.infra import parse_crtsh_response

    entry = {
        "common_name": "SYNTHETIC clearnet domain",
        "name_value": "SYNTHETIC clearnet domain\nwww.SYNTHETIC clearnet domain",
        "serial_number": "AABBCCDD1122",
        "issuer_name": "SYNTHETIC CA",
        "not_before": "2024-01-01",
        "not_after": "2025-01-01",
    }
    matches, truncated = parse_crtsh_response(
        json.dumps([entry]).encode(), "AABBCCDD1122", 20, serial_query=True
    )
    assert len(matches) == 1
    assert matches[0].confidence == "high"
    assert matches[0].domain == "SYNTHETIC clearnet domain"
    assert "www.SYNTHETIC clearnet domain" in matches[0].san
    assert matches[0].serial_number == "AABBCCDD1122"
    assert truncated is False


def test_parse_crtsh_san_match_is_medium_confidence():
    from darknetra.tools.impl.infra import parse_crtsh_response

    entry = {
        "common_name": "SYNTHETIC clearnet domain",
        "name_value": "SYNTHETIC clearnet domain",
        "serial_number": "DIFFERENT1234",
        "issuer_name": "SYNTHETIC CA",
    }
    matches, _ = parse_crtsh_response(
        json.dumps([entry]).encode(), "SYNTHETIC clearnet domain", 20, serial_query=False
    )
    assert matches[0].confidence == "medium"


def test_parse_crtsh_deduplicates_by_serial():
    from darknetra.tools.impl.infra import parse_crtsh_response

    entry = {
        "common_name": "SYNTHETIC",
        "name_value": "SYNTHETIC",
        "serial_number": "DEDUP123",
    }
    payload = json.dumps([entry, entry, entry]).encode()
    matches, _ = parse_crtsh_response(payload, "DEDUP123", 20, serial_query=True)
    assert len(matches) == 1


def test_parse_crtsh_truncates_at_limit():
    from darknetra.tools.impl.infra import parse_crtsh_response

    entries = [
        {
            "common_name": f"SYNTHETIC-{i}.example.test",
            "name_value": f"SYNTHETIC-{i}.example.test",
            "serial_number": f"SER{i:04d}",
        }
        for i in range(30)
    ]
    matches, truncated = parse_crtsh_response(
        json.dumps(entries).encode(), "SYNTHETIC", 5, serial_query=False
    )
    assert len(matches) == 5
    assert truncated is True


def test_parse_crtsh_invalid_json_raises_unavailable():
    from darknetra.tools.impl.infra import parse_crtsh_response

    with pytest.raises(ToolError) as exc:
        parse_crtsh_response(b"SYNTHETIC-not-json", "q", 10, serial_query=False)
    assert exc.value.code == "UNAVAILABLE"


def test_parse_crtsh_non_array_json_raises_unavailable():
    from darknetra.tools.impl.infra import parse_crtsh_response

    with pytest.raises(ToolError) as exc:
        parse_crtsh_response(b'{"error":"SYNTHETIC"}', "q", 10, serial_query=False)
    assert exc.value.code == "UNAVAILABLE"


def test_parse_crtsh_entries_without_domain_are_skipped():
    from darknetra.tools.impl.infra import parse_crtsh_response

    payload = json.dumps([{"serial_number": "SYNTHETIC123"}]).encode()
    matches, _ = parse_crtsh_response(payload, "SYNTHETIC123", 10, serial_query=True)
    assert matches == []


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_fingerprint_input_rejects_non_onion_url():
    from pydantic import ValidationError

    from darknetra.tools.impl.infra import OnionfingerprintInput

    with pytest.raises(ValidationError):
        OnionfingerprintInput(url="https://example.com/page")


def test_fingerprint_input_accepts_valid_onion_url():
    from darknetra.tools.impl.infra import OnionfingerprintInput

    inp = OnionfingerprintInput(url=SYNTHETIC_URL)
    assert inp.url == SYNTHETIC_URL


def test_cert_input_requires_at_least_one_term():
    from pydantic import ValidationError

    from darknetra.tools.impl.infra import ClearnetCertInput

    with pytest.raises(ValidationError):
        ClearnetCertInput()


def test_cert_input_accepts_serial_only():
    from darknetra.tools.impl.infra import ClearnetCertInput

    inp = ClearnetCertInput(serial="AABBCCDD")
    assert inp.serial == "AABBCCDD"
    assert inp.san is None


def test_cert_input_accepts_san_only():
    from darknetra.tools.impl.infra import ClearnetCertInput

    inp = ClearnetCertInput(san="SYNTHETIC.example.test")
    assert inp.san == "SYNTHETIC.example.test"
    assert inp.serial is None


# ---------------------------------------------------------------------------
# Integration stubs — capture gate and quarantine invariants
# ---------------------------------------------------------------------------


@pytest.fixture
def infra_module(monkeypatch):
    import importlib

    module = importlib.import_module("darknetra.tools.impl.infra")
    from darknetra.tools.registry import REGISTRY

    if "onion_fingerprint" not in REGISTRY:
        from dataclasses import replace

        from darknetra.tools.contracts import Lane

        monkeypatch.setitem(
            REGISTRY,
            "onion_fingerprint",
            replace(
                next(iter(REGISTRY.values())),
                name="onion_fingerprint",
                source_class="OSINT_DARK",
                lane=Lane.DARK,
            ),
        )
    if "clearnet_cert_match" not in REGISTRY:
        from dataclasses import replace

        from darknetra.tools.contracts import Lane

        monkeypatch.setitem(
            REGISTRY,
            "clearnet_cert_match",
            replace(
                next(iter(REGISTRY.values())),
                name="clearnet_cert_match",
                source_class="OSINT_SURFACE",
                lane=Lane.SURFACE,
            ),
        )
    return module


async def test_fingerprint_captures_before_parse(monkeypatch, infra_module):
    events: list[str] = []
    capture_result = captured_result()

    async def fake_onionscan(url: str) -> bytes:
        events.append("scan")
        return json.dumps({"online": True}).encode()

    async def fake_capture(ctx, *, spec, locator, fetch):
        await fetch()
        events.append("persisted")
        return capture_result

    real_parse = infra_module.parse_onionscan_output

    def checked_parse(data: bytes) -> dict:
        assert "persisted" in events, "Parser ran before capture persistence"
        events.append("parse")
        return real_parse(data)

    monkeypatch.setattr(infra_module, "_run_onionscan", fake_onionscan)
    monkeypatch.setattr(infra_module, "capture", fake_capture)
    monkeypatch.setattr(infra_module, "parse_onionscan_output", checked_parse)

    ctx = SimpleNamespace(case_id=uuid4(), parent_call_id=None)
    result = await infra_module.onion_fingerprint(
        ctx, infra_module.OnionfingerprintInput(url=SYNTHETIC_URL)
    )
    assert result.evidence_code == "E-0099"
    assert events == ["scan", "persisted", "parse"]


async def test_fingerprint_quarantined_capture_skips_parse(monkeypatch, infra_module):
    async def quarantined(*args, **kwargs):
        return captured_result(quarantined=True)

    def forbidden(*args, **kwargs):
        pytest.fail("Parser ran after quarantined capture")

    monkeypatch.setattr(infra_module, "capture", quarantined)
    monkeypatch.setattr(infra_module, "parse_onionscan_output", forbidden)

    ctx = SimpleNamespace(case_id=uuid4(), parent_call_id=None)
    result = await infra_module.onion_fingerprint(
        ctx, infra_module.OnionfingerprintInput(url=SYNTHETIC_URL)
    )
    assert result.quarantined is True


@pytest.mark.parametrize("code", ["POLICY_DENIED", "NETWORK_REQUIRED", "UNAVAILABLE"])
async def test_fingerprint_gate_failure_propagates_without_parse(
    monkeypatch, infra_module, code
):
    async def denied(*args, **kwargs):
        raise ToolError(code, "SYNTHETIC gate denial")

    def forbidden(*args, **kwargs):
        pytest.fail("Parser ran after denied capture")

    monkeypatch.setattr(infra_module, "capture", denied)
    monkeypatch.setattr(infra_module, "parse_onionscan_output", forbidden)

    ctx = SimpleNamespace(case_id=uuid4(), parent_call_id=None)
    with pytest.raises(ToolError) as exc:
        await infra_module.onion_fingerprint(
            ctx, infra_module.OnionfingerprintInput(url=SYNTHETIC_URL)
        )
    assert exc.value.code == code


async def test_crtsh_captures_before_parse(monkeypatch, infra_module):
    events: list[str] = []
    cr = CaptureResult(
        evidence_code="E-0099",
        evidence_id=uuid4(),
        duplicate=False,
        excerpt="SYNTHETIC crt.sh",
        source_class="OSINT_SURFACE",
        captured_at=datetime.now(UTC),
        quarantined=False,
    )
    crt_payload = json.dumps(
        [
            {
                "common_name": "SYNTHETIC.example.test",
                "name_value": "SYNTHETIC.example.test",
                "serial_number": "AABB1234",
            }
        ]
    ).encode()

    async def fake_fetch(self, url: str) -> Fetched:
        events.append("fetch")
        return Fetched(crt_payload, "application/json", url, 200, {}, datetime.now(UTC))

    async def fake_capture(ctx, *, spec, locator, fetch):
        await fetch()
        events.append("persisted")
        return cr

    real_parse = infra_module.parse_crtsh_response

    def checked_parse(data, query, limit, serial_query):
        assert "persisted" in events, "Parser ran before capture persistence"
        events.append("parse")
        return real_parse(data, query, limit, serial_query)

    monkeypatch.setattr(infra_module.SafeHttp, "fetch", fake_fetch)
    monkeypatch.setattr(infra_module, "capture", fake_capture)
    monkeypatch.setattr(infra_module, "parse_crtsh_response", checked_parse)

    ctx = SimpleNamespace(case_id=uuid4(), parent_call_id=None)
    result = await infra_module.clearnet_cert_match(
        ctx, infra_module.ClearnetCertInput(serial="AABB1234")
    )
    assert result.evidence_code == "E-0099"
    assert result.matches[0].domain == "SYNTHETIC.example.test"
    assert events == ["fetch", "persisted", "parse"]


async def test_crtsh_quarantined_capture_skips_parse(monkeypatch, infra_module):
    cr = CaptureResult(
        evidence_code="E-0099",
        evidence_id=uuid4(),
        duplicate=False,
        excerpt="",
        source_class="OSINT_SURFACE",
        captured_at=datetime.now(UTC),
        quarantined=True,
    )

    async def quarantined(*args, **kwargs):
        return cr

    def forbidden(*args, **kwargs):
        pytest.fail("Parser ran after quarantined capture")

    monkeypatch.setattr(infra_module, "capture", quarantined)
    monkeypatch.setattr(infra_module, "parse_crtsh_response", forbidden)

    ctx = SimpleNamespace(case_id=uuid4(), parent_call_id=None)
    result = await infra_module.clearnet_cert_match(
        ctx, infra_module.ClearnetCertInput(serial="SYNTHETIC")
    )
    assert result.quarantined is True
    assert result.matches == []


@pytest.mark.parametrize("code", ["POLICY_DENIED", "NETWORK_REQUIRED", "RATE_LIMITED"])
async def test_crtsh_gate_failure_propagates_without_parse(monkeypatch, infra_module, code):
    async def denied(*args, **kwargs):
        raise ToolError(code, "SYNTHETIC gate denial")

    def forbidden(*args, **kwargs):
        pytest.fail("Parser ran after denied capture")

    monkeypatch.setattr(infra_module, "capture", denied)
    monkeypatch.setattr(infra_module, "parse_crtsh_response", forbidden)

    ctx = SimpleNamespace(case_id=uuid4(), parent_call_id=None)
    with pytest.raises(ToolError) as exc:
        await infra_module.clearnet_cert_match(
            ctx, infra_module.ClearnetCertInput(san="SYNTHETIC.example.test")
        )
    assert exc.value.code == code
