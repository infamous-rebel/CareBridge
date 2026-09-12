"""Tests for observability middleware: request id, error envelope, logging, size cap (SPEC E)."""

import logging

from fastapi.testclient import TestClient

from src.api.config import get_settings


def test_response_carries_generated_request_id(client):
    """A request without an X-Request-ID gets one generated and echoed back."""
    resp = client.get("/health")
    rid = resp.headers.get("X-Request-ID")
    assert rid and rid != "-"
    # UUID v4 shape: 8-4-4-4-12 hex groups.
    assert len(rid) == 36 and rid.count("-") == 4


def test_incoming_request_id_is_propagated(client):
    """A client-supplied X-Request-ID is preserved on the response."""
    resp = client.get("/health", headers={"X-Request-ID": "rid-propagated-0001"})
    assert resp.headers.get("X-Request-ID") == "rid-propagated-0001"


def test_error_envelope_has_no_stack_trace(client):
    """An unmatched route returns the opaque error envelope, never a traceback."""
    resp = client.get("/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body
    assert "request_id" in body
    text = resp.text.lower()
    assert "traceback" not in text
    assert "site-packages" not in text


def test_unauthenticated_error_envelope_shape(client):
    """A 401 uses the same {error, request_id} envelope."""
    resp = client.get("/auth/me")
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"] == "Not authenticated"
    assert body["request_id"]


def test_logs_carry_request_and_user_context(client, auth_headers, caplog):
    """Records emitted during an authenticated request carry request_id + user_id."""
    with caplog.at_level(logging.INFO):
        resp = client.get("/status/cr-001", headers=auth_headers)
    assert resp.status_code == 200

    stamped = [
        r for r in caplog.records
        if getattr(r, "request_id", "-") not in ("-", None)
        and getattr(r, "user_id", "-") not in ("-", None)
    ]
    assert stamped, "expected at least one log line with request_id and user_id bound"


def test_no_pii_in_logs(client, auth_headers, demo_credentials, caplog):
    """The authenticated user's email (PII) never appears in log output (guardrail J)."""
    with caplog.at_level(logging.INFO):
        client.get("/status/cr-001", headers=auth_headers)
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert demo_credentials["email"] not in blob


def test_request_size_limit_returns_413(monkeypatch, temp_audit_db):
    """A body over MAX_REQUEST_BYTES is rejected with 413 before routing."""
    monkeypatch.setenv("MAX_REQUEST_BYTES", "64")
    get_settings.cache_clear()

    from src.api.main import create_app

    app = create_app()
    with TestClient(app) as c:
        big = {"email": "a" * 120 + "@t.com", "password": "b" * 120}
        resp = c.post("/auth/login", json=big)
    assert resp.status_code == 413
    assert resp.json()["error"] == "Request body too large"
