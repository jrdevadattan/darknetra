import httpx
import pytest
from darknetra_api.main import app

ORIGIN = "http://localhost:3000"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auth_cors_preflight_allows_only_configured_origin() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
        allowed = await client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-csrf-token",
            },
        )
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == ORIGIN
        assert allowed.headers["access-control-allow-credentials"] == "true"
        assert allowed.headers["access-control-allow-origin"] != "*"

        rejected = await client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert rejected.status_code == 400
        assert "access-control-allow-origin" not in rejected.headers
