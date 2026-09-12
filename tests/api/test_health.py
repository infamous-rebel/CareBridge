"""Tests for the public health / readiness / version endpoints (SPEC E)."""


def test_health_returns_ok(client):
    """/health is a bare liveness probe returning {"status": "ok"}."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_is_public(client):
    """/health requires no Authorization header."""
    resp = client.get("/health")  # no auth headers supplied
    assert resp.status_code == 200


def test_ready_checks_dependencies(client):
    """/ready verifies the audit DB and MCP registry, both healthy in tests."""
    resp = client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"]["audit_db"] is True
    assert body["checks"]["mcp_registry"] is True


def test_version_metadata(client):
    """/version exposes build metadata sourced from settings."""
    resp = client.get("/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["app_name"] == "CareBridge API"
    assert body["version"]
    assert body["environment"] == "test"
    assert "git_sha" in body
    assert "build_timestamp" in body


def test_public_endpoints_carry_request_id(client):
    """Every response — even public ones — is tagged with X-Request-ID."""
    for path in ("/health", "/ready", "/version"):
        resp = client.get(path)
        assert resp.headers.get("X-Request-ID"), f"missing request id on {path}"
