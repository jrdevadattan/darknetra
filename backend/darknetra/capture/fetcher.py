"""GET-only transport: validate all DNS answers, then pin connection to one IP."""

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

import httpx

from darknetra.tools.contracts import ToolError

MAX_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class Fetched:
    data: bytes
    mime: str
    url: str
    status: int
    headers: dict[str, str]
    fetched_at: datetime


def public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return ip.is_global and not ip.is_multicast and not ip.is_unspecified and not ip.is_reserved


def validate_url(url: str) -> tuple[str, int]:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").rstrip(".").lower()
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or port not in {80, 443}
            or host == "localhost"
            or host.endswith((".localhost", ".local", ".onion"))
            or any(ord(c) < 33 for c in url)
            or "\\" in url
        ):
            raise ValueError("disallowed URL")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            if not public_ip(host):
                raise ValueError("nonpublic address")
        return host, port
    except ValueError:
        raise ToolError(
            "POLICY_DENIED", "Only public HTTP(S) URLs without credentials are allowed"
        ) from None


class SafeHttp:
    async def fetch(self, url: str, method: str = "GET") -> Fetched:
        if method not in {"GET", "HEAD"}:
            raise ToolError("POLICY_DENIED", "Only GET and HEAD are allowed")
        try:
            async with asyncio.timeout(30):
                return await self._fetch(url, method)
        except TimeoutError:
            raise ToolError("UNAVAILABLE", "Capture timed out") from None
        except (OSError, httpx.HTTPError):
            raise ToolError("NETWORK_REQUIRED", "Public source is unreachable") from None

    async def _fetch(self, url: str, method: str) -> Fetched:
        for redirects in range(4):
            host, port = validate_url(url)
            addresses = await asyncio.get_running_loop().getaddrinfo(
                host, port, type=socket.SOCK_STREAM
            )
            ips = list(dict.fromkeys(str(item[4][0]) for item in addresses))
            if not ips or any(not public_ip(ip) for ip in ips):
                raise ToolError(
                    "POLICY_DENIED", "Destination DNS must resolve only to public addresses"
                )
            # httpcore uses sni_hostname for TLS peer verification; no DNS lookup
            # happens for the pinned IP. Host remains the original HTTP authority.
            original = httpx.URL(url)
            pinned = original.copy_with(host=ips[0])
            headers = {
                "Host": original.netloc.decode("ascii"),
                "User-Agent": "DARKNETRA/0.1 read-only capture",
                "Accept-Encoding": "identity",
            }
            async with httpx.AsyncClient(
                trust_env=False, follow_redirects=False, timeout=20
            ) as client:
                async with client.stream(
                    method, pinned, headers=headers, extensions={"sni_hostname": host}
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        if redirects == 3 or not response.headers.get("location"):
                            raise ToolError("UNAVAILABLE", "Redirect limit exceeded")
                        url = urljoin(url, response.headers["location"])
                        continue
                    if response.status_code == 429:
                        raise ToolError("RATE_LIMITED", "Source rate limit reached")
                    if response.status_code >= 400:
                        raise ToolError(
                            "UNAVAILABLE",
                            "Source returned an unsuccessful response",
                            {"status": response.status_code},
                        )
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise ToolError(
                            "UNAVAILABLE",
                            "Compressed responses are not accepted by the bounded capture transport",
                        )
                    length = response.headers.get("content-length")
                    if length and int(length) > MAX_BYTES:
                        raise ToolError("VALIDATION", "Capture exceeds 10 MiB")
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise ToolError("VALIDATION", "Capture exceeds 10 MiB")
                        chunks.append(chunk)
                    return Fetched(
                        b"".join(chunks),
                        response.headers.get("content-type", "application/octet-stream").split(";")[
                            0
                        ],
                        url,
                        response.status_code,
                        {
                            k: v
                            for k, v in response.headers.items()
                            if k in {"content-type", "last-modified", "etag"}
                        },
                        datetime.now(UTC),
                    )
        raise ToolError("UNAVAILABLE", "Redirect limit exceeded")
