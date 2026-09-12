"""Tests for Firebase Authentication endpoints (SPEC section C extension).

All firebase_admin calls are mocked via pytest monkeypatch — no network calls,
no real Firebase project required.
"""

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enable_firebase(monkeypatch):
    """Set env vars to enable Firebase auth for the test."""
    monkeypatch.setenv("FIREBASE_AUTH_ENABLED", "true")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "carebridge-675df")
    from src.api.config import get_settings
    get_settings.cache_clear()


def _mock_firebase_verify(monkeypatch, *, email_verified=True, uid="fb-uid-123",
                          email="firebase@example.com", name="Firebase User"):
    """Mock verify_firebase_id_token to return a controlled FirebaseUser."""
    from src.api.firebase_auth import FirebaseUser

    def _verify(id_token):
        if id_token == "invalid-token":
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Firebase ID token",
            )
        if not email_verified:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email not verified. Please verify your email address.",
            )
        return FirebaseUser(
            uid=uid, email=email, name=name, email_verified=email_verified,
        )

    monkeypatch.setattr(
        "src.api.routers.auth.verify_firebase_id_token", _verify
    )


def _mock_firebase_create_token(monkeypatch, token="mock-custom-token"):
    """Mock create_firebase_custom_token to return a fixed string."""
    monkeypatch.setattr(
        "src.api.routers.auth.create_firebase_custom_token",
        lambda uid, claims: token,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_exchange_valid_token_creates_user(client, monkeypatch):
    """Exchange with a valid token creates a new user and returns tokens."""
    _enable_firebase(monkeypatch)
    _mock_firebase_verify(monkeypatch)
    _mock_firebase_create_token(monkeypatch)

    resp = client.post("/auth/firebase/exchange", json={"id_token": "valid-token"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["custom_token"] == "mock-custom-token"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "firebase@example.com"
    assert body["user"]["role"] == "caregiver_primary"


def test_exchange_existing_email_links_firebase_uid(client, monkeypatch):
    """Exchange with an existing email links the Firebase UID."""
    _enable_firebase(monkeypatch)
    # Use the demo user's email so it already exists.
    _mock_firebase_verify(
        monkeypatch, uid="fb-uid-link", email="demo@carebridge.test",
    )
    _mock_firebase_create_token(monkeypatch)

    resp = client.post("/auth/firebase/exchange", json={"id_token": "valid-token"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == "demo@carebridge.test"

    # Verify the firebase_uid was linked.
    from src.api import user_store
    user = user_store.get_user_by_firebase_uid("fb-uid-link")
    assert user is not None
    assert user["email"] == "demo@carebridge.test"


def test_exchange_existing_firebase_uid_returns_same_user(client, monkeypatch):
    """Exchange with an already-linked Firebase UID returns the same user."""
    _enable_firebase(monkeypatch)
    _mock_firebase_verify(monkeypatch, uid="fb-uid-123")
    _mock_firebase_create_token(monkeypatch)

    # First exchange creates the user.
    resp1 = client.post("/auth/firebase/exchange", json={"id_token": "valid-token"})
    assert resp1.status_code == 200
    user_id_1 = resp1.json()["user"]["user_id"]

    # Second exchange returns the same user.
    resp2 = client.post("/auth/firebase/exchange", json={"id_token": "valid-token"})
    assert resp2.status_code == 200
    user_id_2 = resp2.json()["user"]["user_id"]
    assert user_id_1 == user_id_2


def test_exchange_invalid_token_returns_401(client, monkeypatch):
    """Exchange with an invalid token returns 401."""
    _enable_firebase(monkeypatch)
    _mock_firebase_verify(monkeypatch)  # Will raise on "invalid-token"

    resp = client.post("/auth/firebase/exchange", json={"id_token": "invalid-token"})
    assert resp.status_code == 401


def test_exchange_unverified_email_returns_401(client, monkeypatch):
    """Exchange with an unverified email returns 401."""
    _enable_firebase(monkeypatch)
    _mock_firebase_verify(monkeypatch, email_verified=False)

    resp = client.post("/auth/firebase/exchange", json={"id_token": "valid-token"})
    assert resp.status_code == 401
    assert "not verified" in resp.json()["error"]


def test_firebase_config_enabled(client, monkeypatch):
    """/auth/firebase/config returns enabled=True when configured."""
    _enable_firebase(monkeypatch)

    resp = client.get("/auth/firebase/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["project_id"] == "carebridge-675df"


def test_firebase_config_disabled(client):
    """/auth/firebase/config returns enabled=False when not configured."""
    # Default: FIREBASE_AUTH_ENABLED=false.
    resp = client.get("/auth/firebase/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False


def test_verify_returns_profile_without_tokens(client, monkeypatch):
    """/auth/firebase/verify returns the profile without issuing tokens."""
    _enable_firebase(monkeypatch)
    _mock_firebase_verify(monkeypatch, uid="fb-verify-uid", email="verify@test.com",
                          name="Verify User")

    resp = client.post("/auth/firebase/verify", json={"id_token": "valid-token"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["uid"] == "fb-verify-uid"
    assert body["email"] == "verify@test.com"
    assert body["name"] == "Verify User"
    # No tokens in the verify response.
    assert "access_token" not in body
    assert "custom_token" not in body


def test_exchange_when_firebase_disabled_returns_503(client):
    """Exchange returns 503 when Firebase is not configured."""
    # Default: FIREBASE_AUTH_ENABLED=false.
    resp = client.post("/auth/firebase/exchange", json={"id_token": "any"})
    assert resp.status_code == 503
    assert "not configured" in resp.json()["error"]


def test_verify_when_firebase_disabled_returns_503(client):
    """Verify returns 503 when Firebase is not configured."""
    resp = client.post("/auth/firebase/verify", json={"id_token": "any"})
    assert resp.status_code == 503
