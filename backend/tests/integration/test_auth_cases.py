from uuid import uuid4

import pytest


@pytest.mark.integration
async def test_auth_case_lifecycle_and_membership_isolation(client, actor_login):
    await actor_login()
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    case = await client.post(
        "/api/v1/cases",
        json={"title": "SYNTHETIC case", "demo": True, "authority_ref": "SYNTHETIC authority"},
    )
    assert case.status_code == 201, case.text
    data = case.json()
    assert data["my_role"] == "OWNER"
    assert data["authority_ref_present"]
    assert "authority_ref_enc" not in data
    path = f"/api/v1/cases/{data['id']}"
    csrf = client.headers.pop("X-CSRF-Token")
    denied = await client.patch(path, json={"title": "No CSRF"})
    assert denied.status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    closed = await client.post(path + "/close", json={"reason": "SYNTHETIC test close"})
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "CLOSED"
    reopened = await client.post(path + "/reopen", json={"reason": "SYNTHETIC test reopen"})
    assert reopened.json()["status"] == "OPEN"
    await actor_login()
    hidden = await client.get(path)
    unknown = await client.get(f"/api/v1/cases/{uuid4()}")
    assert hidden.status_code == unknown.status_code == 404
    assert hidden.json()["error"]["message"] == unknown.json()["error"]["message"]
    visible = await client.get("/api/v1/cases")
    assert data["id"] not in {case["id"] for case in visible.json()["items"]}


@pytest.mark.integration
async def test_refresh_reuse_revokes_new_session(client, actor_login):
    """Scenarios 48 and 49: consumed refresh credentials cannot be reused."""
    await actor_login()
    old_cookies = dict(client.cookies)
    rotated = await client.post("/api/v1/auth/refresh")
    assert rotated.status_code == 200, rotated.text
    new_cookies = dict(client.cookies)
    client.cookies.clear()
    client.cookies.update(old_cookies)
    client.headers["X-CSRF-Token"] = old_cookies["darknetra_csrf"]
    reused = await client.post("/api/v1/auth/refresh")
    assert reused.status_code == 401, reused.text
    client.cookies.clear()
    client.cookies.update(new_cookies)
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 401


@pytest.mark.integration
async def test_forced_password_change_and_scoped_service_token(client, actor_login):
    """Scenario 44: an alerts-only token never inherits full owner permissions."""
    await actor_login(forced=True)
    forbidden = await client.get("/api/v1/cases")
    assert forbidden.status_code == 403
    change = await client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "SYNTHETIC fixture password 123",
            "new_password": "SYNTHETIC replacement 456",
        },
    )
    assert change.status_code == 204, change.text
    created = await client.post(
        "/api/v1/cases", json={"title": "SYNTHETIC token case", "demo": True}
    )
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    token = await client.post(
        "/api/v1/auth/tokens",
        json={"name": "SYNTHETIC alerts reader", "scopes": ["alerts:read"], "case_id": cid},
    )
    assert token.status_code == 201, token.text
    client.cookies.clear()
    client.headers["Authorization"] = "Bearer " + token.json()["token"]
    denied = await client.post(f"/api/v1/cases/{cid}/threads", json={"title": "SYNTHETIC denied"})
    assert denied.status_code == 403, denied.text
