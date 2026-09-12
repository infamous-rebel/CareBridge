"""Tests for LLM provider introspection on ``GET /ready`` (spec F).

``/ready`` must tell an operator which provider the deployment resolved to and
whether it can build a model adapter — without ever letting a missing API key
take the whole service out of rotation.

Kept separate from ``tests/api/test_health.py`` so the existing readiness
contract stays untouched; these cases only add to it.
"""

import pytest

from src.api.config import get_settings
from src.runtime.model_factory import reset_model_cache

# Syntactically plausible, non-functional key. Adapter construction is offline,
# so nothing is ever sent to a provider.
DUMMY_GEMINI_KEY = "AIzaSyTEST-READY-PROBE-0000000000"
DUMMY_GROQ_KEY = "gsk-test-only-not-a-real-key"


def _apply(monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
    """Set provider env vars after the app has started, then drop stale caches.

    The ``client`` fixture runs the app lifespan (which populates the settings
    cache) before the test body, so the caches must be cleared for the handler
    to observe the new configuration.
    """
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    reset_model_cache()


def test_ready_reports_llm_unavailable_without_credentials(client) -> None:
    """No key configured: reported honestly, but the service stays ready."""
    resp = client.get("/ready")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["llm_provider"] == "gemini", "gemini is the documented default"
    assert body["llm_available"] is False
    # The existing readiness contract is unchanged: audit DB + MCP registry.
    assert body["status"] == "ok"
    assert body["checks"]["audit_db"] is True
    assert body["checks"]["mcp_registry"] is True


def test_ready_reports_llm_available_when_configured(client, monkeypatch) -> None:
    """A configured provider is reported as available."""
    _apply(monkeypatch, LLM_PROVIDER="gemini", GEMINI_API_KEY=DUMMY_GEMINI_KEY)

    resp = client.get("/ready")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["llm_provider"] == "gemini"
    assert body["llm_available"] is True
    assert body["status"] == "ok"


def test_ready_reflects_provider_switch_by_env_only(client, monkeypatch) -> None:
    """Swapping provider changes the payload with no code change or restart."""
    _apply(monkeypatch, LLM_PROVIDER="groq", GROQ_API_KEY=DUMMY_GROQ_KEY)

    body = client.get("/ready").json()
    assert body["llm_provider"] == "groq"
    assert body["llm_available"] is True

    # Ollama needs no credential at all, so it reports available with just a host.
    _apply(monkeypatch, LLM_PROVIDER="ollama", OLLAMA_HOST="http://localhost:11434")

    body = client.get("/ready").json()
    assert body["llm_provider"] == "ollama"
    assert body["llm_available"] is True


def test_ready_does_not_leak_credentials(client, monkeypatch) -> None:
    """The API key must not appear anywhere in the readiness payload."""
    _apply(monkeypatch, LLM_PROVIDER="gemini", GEMINI_API_KEY=DUMMY_GEMINI_KEY)

    resp = client.get("/ready")

    assert DUMMY_GEMINI_KEY not in resp.text
    assert DUMMY_GEMINI_KEY.lower() not in resp.text.lower()
