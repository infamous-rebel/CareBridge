"""Tests for authentication: login, refresh, /me, and token-type enforcement (SPEC C)."""


def test_login_success(client, demo_credentials):
    """Valid credentials yield an access + refresh token pair."""
    resp = client.post("/auth/login", json=demo_credentials)
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["access_token"] != body["refresh_token"]


def test_login_wrong_password_is_401(client, demo_credentials):
    """A wrong password is rejected with 401 and no token leakage."""
    resp = client.post(
        "/auth/login",
        json={"email": demo_credentials["email"], "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert "access_token" not in resp.json()


def test_login_unknown_email_is_401(client):
    """An unknown email is rejected identically to a wrong password."""
    resp = client.post(
        "/auth/login", json={"email": "nobody@carebridge.test", "password": "x"}
    )
    assert resp.status_code == 401


def test_login_invalid_email_is_422(client):
    """Pydantic validation rejects a malformed email before auth runs."""
    resp = client.post(
        "/auth/login", json={"email": "not-an-email", "password": "whatever"}
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "Request validation failed"
    assert "request_id" in body


def test_me_authenticated(client, auth_headers, demo_credentials):
    """/auth/me returns the current user's public view."""
    resp = client.get("/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == demo_credentials["email"]
    assert body["role"] == "caregiver_primary"
    assert body["user_id"]


def test_me_requires_auth(client):
    """/auth/me without a bearer token is 401 with the standard envelope."""
    resp = client.get("/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"] == "Not authenticated"


def test_me_invalid_token_is_401(client):
    """A garbage bearer token is rejected with 401."""
    resp = client.get("/auth/me", headers={"Authorization": "Bearer not.a.real.token"})
    assert resp.status_code == 401


def test_refresh_success(client, demo_credentials):
    """A valid refresh token exchanges for a fresh token pair."""
    login = client.post("/auth/login", json=demo_credentials).json()
    resp = client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"


def test_refresh_rejects_access_token(client, demo_credentials):
    """An access token must not be accepted by the refresh endpoint (type claim)."""
    login = client.post("/auth/login", json=demo_credentials).json()
    resp = client.post("/auth/refresh", json={"refresh_token": login["access_token"]})
    assert resp.status_code == 401


def test_refresh_token_rejected_on_protected_route(client, demo_credentials):
    """Token types are not interchangeable: a refresh token cannot access /me."""
    login = client.post("/auth/login", json=demo_credentials).json()
    resp = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {login['refresh_token']}"}
    )
    assert resp.status_code == 401
