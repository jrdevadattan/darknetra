import asyncio
import socket
from unittest.mock import AsyncMock

import httpx
import pytest

from darknetra.capture.fetcher import MAX_BYTES, SafeHttp
from darknetra.tools.contracts import ToolError


@pytest.fixture
async def public_dns(monkeypatch):
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        loop,
        "getaddrinfo",
        AsyncMock(
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        ),
    )


async def test_capture_pins_ip_host_and_tls_name(monkeypatch, public_dns):
    original = httpx.AsyncClient
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200, content=b"SYNTHETIC content", headers={"content-type": "text/plain"}
        )

    def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    fetched = await SafeHttp().fetch("https://synthetic.example.test/")
    assert fetched.data == b"SYNTHETIC content"
    assert requests[0].url.host == "93.184.216.34"
    assert requests[0].headers["Host"] == "synthetic.example.test"
    assert requests[0].extensions["sni_hostname"] == "synthetic.example.test"
    assert "cookie" not in requests[0].headers
    assert "authorization" not in requests[0].headers


async def test_capture_redirect_private_denied(monkeypatch, public_dns):
    original = httpx.AsyncClient

    def handler(request):
        return httpx.Response(302, headers={"location": "http://127.0.0.1/internal"})

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
    )
    with pytest.raises(ToolError) as error:
        await SafeHttp().fetch("https://synthetic.example.test/")
    assert error.value.code == "POLICY_DENIED"


async def test_capture_refuses_oversize_before_buffer(monkeypatch, public_dns):
    original = httpx.AsyncClient

    def handler(request):
        return httpx.Response(200, headers={"content-length": str(MAX_BYTES + 1)})

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
    )
    with pytest.raises(ToolError) as error:
        await SafeHttp().fetch("https://synthetic.example.test/")
    assert error.value.code == "VALIDATION"


async def test_capture_mixed_dns_private_is_denied(monkeypatch):
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        loop,
        "getaddrinfo",
        AsyncMock(
            return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443)),
            ]
        ),
    )
    with pytest.raises(ToolError) as error:
        await SafeHttp().fetch("https://synthetic.example.test/")
    assert error.value.code == "POLICY_DENIED"


async def test_capture_post_never_sent():
    with pytest.raises(ToolError) as error:
        await SafeHttp().fetch("https://synthetic.example.test/", method="POST")
    assert error.value.code == "POLICY_DENIED"
