"""Tests for the authenticated status summary endpoint (SPEC F)."""


def test_status_authenticated(client, auth_headers):
    """An authenticated caregiver gets a StatusSummary for the recipient."""
    resp = client.get("/status/cr-001", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["care_recipient_id"] == "cr-001"
    assert isinstance(body["summary_text"], str)
    assert isinstance(body["recent_events"], list)
    assert isinstance(body["pending_actions"], list)


def test_status_requires_auth(client):
    """/status is protected — no bearer token means 401."""
    resp = client.get("/status/cr-001")
    assert resp.status_code == 401


def test_status_reflects_pending_action(client, auth_headers, write_audit):
    """A pending audit event surfaces in the summary's pending_actions."""
    write_audit(action_type="order_refill", outcome="pending", care_recipient_id="cr-001")
    resp = client.get("/status/cr-001", headers=auth_headers)
    assert resp.status_code == 200
    pending = resp.json()["pending_actions"]
    assert any(a["action_type"] == "order_refill" for a in pending)


def test_status_viewer_can_read(client, make_user):
    """Any authenticated role (including viewer) may read status."""
    viewer = make_user(role="viewer")
    resp = client.get("/status/cr-001", headers=viewer)
    assert resp.status_code == 200
