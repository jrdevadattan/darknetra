"""Infrastructure-fingerprinting adapters for dark-web deanonymisation.

onion_fingerprint: runs OnionScan (subprocess, optional binary) against an onion URL
through the capture gate, then parses the JSON report into a bounded excerpt.

clearnet_cert_match: queries crt.sh for clearnet domains sharing a TLS certificate
serial or SAN, captured as immutable evidence before returning a bounded excerpt.

Both tools go through the capture gate and return evidence-linked excerpts following
the same invariants as robin_search and public_page_read.

Note on entity-type wiring: The captured JSON evidence from both tools flows through
the existing extract_indicators pipeline. That pipeline extracts ONION_LOCATOR and URL
observations, which feed correlate_entities and graph without schema changes. Full
first-class INFRASTRUCTURE_FINGERPRINT and CLEARNET_MATCH entity types in the
observation/entity tables require a CHECK-constraint migration (ask before writing).
"""

import asyncio
import json
import shutil
from datetime import UTC, datetime
from typing import Any, Literal, cast
from urllib.parse import urlencode, urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator

from darknetra.api.v1.schemas.common import SourceClass
from darknetra.capture.fetcher import Fetched, SafeHttp
from darknetra.capture.gate import CaptureResult, capture
from darknetra.tools.contracts import ToolContext, ToolError
from darknetra.tools.impl.evidence import Input
from darknetra.tools.presentation import emit_parsing

MAX_PARSE_BYTES = 2 * 1024 * 1024


# ---------------------------------------------------------------------------
# onion_fingerprint
# ---------------------------------------------------------------------------


class OnionfingerprintInput(Input):
    url: str = Field(min_length=10, max_length=4096)

    @field_validator("url")
    @classmethod
    def must_be_onion_url(cls, v: str) -> str:
        parsed = urlsplit(v)
        host = (parsed.hostname or "").rstrip(".").lower()
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("URL scheme must be http or https")
        if not host.endswith(".onion"):
            raise ValueError("onion_fingerprint requires a .onion URL")
        return v


class TlsCert(BaseModel):
    cn: str | None = None
    san: list[str] = Field(default_factory=list, max_length=20)
    serial: str | None = None
    issuer: str | None = None


class OnionFingerprintOutput(CaptureResult):
    source_class: SourceClass
    tls_cert: TlsCert | None = None
    server_header: str | None = None
    powered_by: str | None = None
    exposed_paths: list[str] = Field(default_factory=list, max_length=50)
    status_page_found: bool = False
    scope: str = (
        "Infrastructure fingerprint from OnionScan. Observed TLS attributes, headers, "
        "and exposed paths may correlate with clearnet services; findings require "
        "analyst review before confirming any identity link."
    )


def parse_onionscan_output(data: bytes) -> dict[str, Any]:
    """Parse OnionScan JSON output into bounded fingerprint fields.

    OnionScan v0.2 emits a JSON object with responseHeaders, certificate,
    webdetects, and linkedOnions. This parser is deliberately lenient on
    missing keys so partial scans still produce a useful excerpt.
    """
    try:
        payload = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        raise ToolError("UNAVAILABLE", "OnionScan output is not valid JSON") from None
    if not isinstance(payload, dict):
        raise ToolError("UNAVAILABLE", "OnionScan returned an unexpected JSON structure")

    # TLS certificate fields
    cert_raw = payload.get("certificate") or {}
    tls_cert: TlsCert | None = None
    if isinstance(cert_raw, dict) and cert_raw:
        sans = cert_raw.get("dnsNames") or cert_raw.get("san") or []
        tls_cert = TlsCert(
            cn=_str(cert_raw.get("commonName") or cert_raw.get("cn")),
            san=[s for s in sans if isinstance(s, str)][:20],
            serial=_str(cert_raw.get("serialNumber") or cert_raw.get("serial")),
            issuer=_str(cert_raw.get("issuer")),
        )

    # Response headers
    headers: dict[str, Any] = payload.get("responseHeaders") or {}
    server_header = _str(headers.get("Server") or headers.get("server"))
    powered_by = _str(headers.get("X-Powered-By") or headers.get("x-powered-by"))

    # Exposed paths / linked onions (capped)
    linked = payload.get("linkedOnions") or []
    exposed = [p for p in linked if isinstance(p, str)][:50]

    # Status page detection from webdetects flags
    checks: dict[str, Any] = payload.get("webdetects") or {}
    status_page = any(
        bool(checks.get(key))
        for key in ("serverStatus", "phpInfo", "openDirectories", "robotsTxt")
    )

    return {
        "tls_cert": tls_cert.model_dump() if tls_cert else None,
        "server_header": server_header,
        "powered_by": powered_by,
        "exposed_paths": exposed,
        "status_page_found": status_page,
    }


async def _run_onionscan(url: str) -> bytes:
    binary = shutil.which("onionscan") or shutil.which("onionscan-linux")
    if not binary:
        raise ToolError(
            "UNAVAILABLE",
            "OnionScan binary is not installed; add the onionscan profile to the Compose stack",
        )
    try:
        async with asyncio.timeout(120):
            proc = await asyncio.create_subprocess_exec(
                binary,
                "--json",
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
    except TimeoutError:
        raise ToolError("UNAVAILABLE", "OnionScan timed out after 120 s") from None
    except OSError as exc:
        raise ToolError("UNAVAILABLE", f"OnionScan process error: {exc}") from exc
    if not stdout:
        raise ToolError("UNAVAILABLE", "OnionScan produced no output")
    if len(stdout) > MAX_PARSE_BYTES:
        raise ToolError("VALIDATION", "OnionScan output exceeds 2 MiB parsing limit")
    return stdout


async def onion_fingerprint(ctx: ToolContext, args: BaseModel) -> BaseModel:
    from darknetra.tools.registry import REGISTRY

    request = cast(OnionfingerprintInput, args)
    fetched_data: bytes | None = None

    async def fetch() -> Fetched:
        nonlocal fetched_data
        data = await _run_onionscan(request.url)
        fetched_data = data
        return Fetched(data, "application/json", request.url, 200, {}, datetime.now(UTC))

    result = await capture(
        ctx, spec=REGISTRY["onion_fingerprint"], locator=request.url, fetch=fetch
    )
    output = OnionFingerprintOutput.model_validate(result.model_dump())
    if result.quarantined:
        return output
    if fetched_data is None:
        raise ToolError("UNAVAILABLE", "Capture did not provide OnionScan output")
    await emit_parsing(ctx, "onion_fingerprint", result)
    parsed = parse_onionscan_output(fetched_data)
    return OnionFingerprintOutput(**result.model_dump(), **parsed)


# ---------------------------------------------------------------------------
# clearnet_cert_match
# ---------------------------------------------------------------------------


class ClearnetCertInput(Input):
    serial: str | None = Field(None, max_length=100)
    san: str | None = Field(None, max_length=253)
    limit: int = Field(20, ge=1, le=50)

    @model_validator(mode="after")
    def at_least_one_query_term(self) -> "ClearnetCertInput":
        if self.serial is None and self.san is None:
            raise ValueError("Provide at least one of serial or san")
        return self


class ClearnetMatch(BaseModel):
    domain: str = Field(max_length=253)
    serial_number: str | None = None
    san: list[str] = Field(default_factory=list, max_length=20)
    issuer: str | None = None
    not_before: str | None = None
    not_after: str | None = None
    confidence: Literal["high", "medium"]


class ClearnetCertOutput(CaptureResult):
    source_class: SourceClass
    query: str
    matches: list[ClearnetMatch] = Field(default_factory=list, max_length=50)
    truncated: bool = False
    scope: str = (
        "Certificate transparency records from crt.sh. Serial match = same certificate "
        "(high confidence); SAN overlap = shared infrastructure (medium confidence). "
        "Neither result confirms server identity without corroborating evidence."
    )


def parse_crtsh_response(
    data: bytes, query: str, limit: int, serial_query: bool
) -> tuple[list[ClearnetMatch], bool]:
    """Parse crt.sh JSON array into bounded ClearnetMatch records.

    crt.sh returns a JSON array of certificate log entries. Each entry has
    common_name, name_value (newline-separated SANs), serial_number, and
    issuer_name.
    """
    try:
        payload = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        raise ToolError("UNAVAILABLE", "crt.sh returned invalid JSON") from None
    if not isinstance(payload, list):
        raise ToolError("UNAVAILABLE", "crt.sh returned an unexpected JSON structure")

    seen_serials: set[str] = set()
    matches: list[ClearnetMatch] = []
    truncated = False

    for entry in payload[:200]:
        if not isinstance(entry, dict):
            continue
        serial = _str(entry.get("serial_number"))
        common_name = _str(entry.get("common_name")) or ""
        name_value = _str(entry.get("name_value")) or ""
        issuer = _str(entry.get("issuer_name"))
        not_before = _str(entry.get("not_before"))
        not_after = _str(entry.get("not_after"))

        # Deduplicate by serial; multiple CT logs can carry the same cert.
        dedup_key = serial or common_name
        if dedup_key in seen_serials:
            continue
        seen_serials.add(dedup_key)

        san_list = [
            s.strip() for s in name_value.split("\n") if s.strip() and len(s.strip()) <= 253
        ][:20]
        domain = common_name or (san_list[0] if san_list else "")
        if not domain:
            continue

        # Confidence: serial query + matching serial → high; SAN match only → medium.
        if serial_query and serial and serial.lower() == query.lower():
            confidence: Literal["high", "medium"] = "high"
        else:
            confidence = "medium"

        if len(matches) >= limit:
            truncated = True
            break
        matches.append(
            ClearnetMatch(
                domain=domain[:253],
                serial_number=serial,
                san=san_list,
                issuer=issuer,
                not_before=not_before,
                not_after=not_after,
                confidence=confidence,
            )
        )

    return matches, truncated


async def clearnet_cert_match(ctx: ToolContext, args: BaseModel) -> BaseModel:
    from darknetra.tools.registry import REGISTRY

    request = cast(ClearnetCertInput, args)
    # Prefer serial when both are supplied; serial is more specific.
    query = request.serial if request.serial is not None else request.san
    assert query is not None  # model_validator guarantees at least one
    url = "https://crt.sh/?" + urlencode({"q": query, "output": "json"})

    fetched_data: bytes | None = None

    async def fetch() -> Fetched:
        nonlocal fetched_data
        f = await SafeHttp().fetch(url)
        if len(f.data) > MAX_PARSE_BYTES:
            raise ToolError("VALIDATION", "crt.sh response exceeds 2 MiB parsing limit")
        fetched_data = f.data
        return f

    result = await capture(
        ctx, spec=REGISTRY["clearnet_cert_match"], locator=url, fetch=fetch
    )
    output_base = result.model_dump()
    if result.quarantined:
        return ClearnetCertOutput(**output_base, query=query)
    if fetched_data is None:
        raise ToolError("UNAVAILABLE", "Capture did not provide crt.sh response")
    await emit_parsing(ctx, "clearnet_cert_match", result)
    matches, truncated = parse_crtsh_response(
        fetched_data, query, request.limit, serial_query=request.serial is not None
    )
    return ClearnetCertOutput(**output_base, query=query, matches=matches, truncated=truncated)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _str(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:2000]
