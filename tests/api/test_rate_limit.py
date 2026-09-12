"""Tests for auth-endpoint rate limiting (SPEC E).

The auth limit is read through a callable (``auth_limit``), so tightening
``AUTH_RATE_LIMIT`` and clearing the settings cache takes effect at request time
without rebuilding the limiter. ``limiter.reset()`` clears the in-memory counters
so the burst starts from zero.
"""

from src.api.config import get_settings
from src.api.rate_limit import limiter


def test_auth_rate_limit_returns_429(client, demo_credentials, monkeypatch):
    """After the configured burst, /auth/login returns 429."""
    monkeypatch.setenv("AUTH_RATE_LIMIT", "3/minute")
    get_settings.cache_clear()
    limiter.reset()

    codes = [
        client.post("/auth/login", json=demo_credentials).status_code
        for _ in range(6)
    ]
    assert codes[:3] == [200, 200, 200]
    assert codes[3:] == [429, 429, 429]


def test_rate_limited_response_shape(client, demo_credentials, monkeypatch):
    """A 429 uses the standard error envelope (no stack trace)."""
    monkeypatch.setenv("AUTH_RATE_LIMIT", "1/minute")
    get_settings.cache_clear()
    limiter.reset()

    client.post("/auth/login", json=demo_credentials)  # consumes the single slot
    resp = client.post("/auth/login", json=demo_credentials)
    assert resp.status_code == 429
    body = resp.json()
    assert body["error"] == "Rate limit exceeded"
    assert "request_id" in body


def test_health_is_exempt_from_rate_limit(client, monkeypatch):
    """/health is limiter-exempt, so a burst never 429s."""
    monkeypatch.setenv("AUTH_RATE_LIMIT", "1/minute")
    get_settings.cache_clear()
    limiter.reset()

    codes = [client.get("/health").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 200, 200]
