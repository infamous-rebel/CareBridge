"""Shared fixtures for the CareBridge REST API tests (SPEC section I).

Design notes
------------
- The root ``conftest.temp_audit_db`` (autouse) patches the audit DB to a
  per-test temp file and resets Supervisor state. Every fixture that builds the
  app depends on it explicitly so the patch window is guaranteed to be active
  before the app lifespan runs (the lifespan calls ``init_audit_db``).
- ``api_env`` (autouse) redirects the *users* DB to a temp file, forces a low
  bcrypt cost (fast hashing), enables DEMO_MODE (so the demo user seeds), and
  raises the rate limits so ordinary tests never trip 429. The settings cache is
  cleared before and after so no test observes stale config.
- ``reset_limiter`` (autouse) clears slowapi's in-memory counters around each
  test so a burst in one test never leaks into the next.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.config import get_settings
from src.api.rate_limit import limiter

# Deterministic, non-secret demo credentials (tests only).
DEMO_EMAIL = "demo@carebridge.test"
DEMO_PASSWORD = "TestPassw0rd!123"
_TEST_JWT_SECRET = "test-only-jwt-secret-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def api_env(tmp_path, monkeypatch):
    """Point the API at temp DBs and fast, deterministic settings for each test."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")  # fast hashing; allowed in demo mode
    monkeypatch.setenv("JSON_LOGGING", "false")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("AUTH_DB_PATH", str(tmp_path / "test_auth.db"))
    monkeypatch.setenv("AUTH_RATE_LIMIT", "1000/minute")
    monkeypatch.setenv("GLOBAL_RATE_LIMIT", "100000/minute")
    monkeypatch.setenv("DEMO_USER_EMAIL", DEMO_EMAIL)
    monkeypatch.setenv("DEMO_USER_PASSWORD", DEMO_PASSWORD)
    monkeypatch.setenv("DEMO_USER_ROLE", "caregiver_primary")
    monkeypatch.setenv("JWT_SECRET_KEY", _TEST_JWT_SECRET)
    monkeypatch.setenv("FIREBASE_AUTH_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def reset_limiter():
    """Clear rate-limit counters before and after every test."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def app(api_env, temp_audit_db):
    """A freshly built FastAPI app inside the patched audit + temp users DB."""
    from src.api.main import create_app

    return create_app()


@pytest.fixture
def client(app):
    """A ``TestClient`` with the lifespan running (inits DBs, seeds demo user)."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def demo_credentials():
    """Login body for the seeded demo caregiver (matches ``api_env``)."""
    return {"email": DEMO_EMAIL, "password": DEMO_PASSWORD}


@pytest.fixture
def auth_headers(client, demo_credentials):
    """Bearer headers for the seeded demo caregiver (primary role)."""
    resp = client.post("/auth/login", json=demo_credentials)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def make_user(client):
    """Factory: create a user with a role and return its bearer headers.

    The user is written to the (temp) users DB and an access token is minted
    directly, so tests can exercise RBAC without extra login round-trips.
    ``client`` is requested so the users table exists (lifespan ran) first.
    """
    from src.api import user_store
    from src.api.security import create_access_token, hash_password

    def _make(role: str = "viewer", email: str | None = None,
              care_recipient_id: str = "cr-001") -> dict:
        email = email or f"{role}-{uuid4().hex[:8]}@carebridge.test"
        user = user_store.create_user(
            email=email,
            password_hash=hash_password("Str0ngPassw0rd!xyz"),
            role=role,
            full_name="Test User",
            care_recipient_id=care_recipient_id,
        )
        token = create_access_token(user["user_id"], user["role"])
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
def write_audit(temp_audit_db):
    """Factory: append an audit event to the patched temp audit DB.

    Returns the generated ``event_id``. Uses the audit layer's patched defaults
    (see root ``conftest``), so no explicit ``db_path`` is required.
    """
    from src.models.audit_log import write_audit_event

    def _write(actor: str = "supervisor", action_type: str = "manual_review",
               care_recipient_id: str = "cr-001", rationale: str = "Test event",
               outcome: str = "success", correlation_id: str | None = None,
               authorization_ref: str | None = None) -> str:
        return write_audit_event(
            actor=actor,
            action_type=action_type,
            care_recipient_id=care_recipient_id,
            rationale=rationale,
            outcome=outcome,
            correlation_id=correlation_id or str(uuid4()),
            authorization_ref=authorization_ref,
        )

    return _write
