"""Tests for the approval queue and human approve/reject decisions (SPEC F)."""


def test_approvals_requires_auth(client):
    """/approvals is protected — no bearer token means 401."""
    assert client.get("/approvals").status_code == 401


def test_queue_lists_pending(client, auth_headers, write_audit):
    """A pending audit event appears in the approval queue."""
    write_audit(action_type="order_refill", outcome="pending", care_recipient_id="cr-001")
    resp = client.get("/approvals", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()
    assert any(a["action_type"] == "order_refill" for a in items)
    assert all(a["status"] == "pending" for a in items)


def test_reject_removes_from_queue(client, auth_headers, write_audit):
    """Rejecting a pending action resolves it and drops it from the queue."""
    action_id = write_audit(action_type="manual_review", outcome="pending")
    resp = client.post(f"/approvals/{action_id}/reject", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    queue = client.get("/approvals", headers=auth_headers).json()
    assert all(a["action_id"] != action_id for a in queue)


def test_approve_resolves_action(client, auth_headers, write_audit):
    """Approving a pending action resolves it and drops it from the queue."""
    action_id = write_audit(action_type="manual_review", outcome="pending")
    resp = client.post(f"/approvals/{action_id}/approve", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    queue = client.get("/approvals", headers=auth_headers).json()
    assert all(a["action_id"] != action_id for a in queue)


def test_decide_unknown_action_is_404(client, auth_headers):
    """Deciding on a non-existent action id returns 404."""
    resp = client.post("/approvals/does-not-exist/reject", headers=auth_headers)
    assert resp.status_code == 404


def test_viewer_cannot_decide(client, make_user, write_audit):
    """Viewers lack the caregiver role required to approve/reject (403)."""
    viewer = make_user(role="viewer")
    action_id = write_audit(action_type="manual_review", outcome="pending")
    resp = client.post(f"/approvals/{action_id}/approve", headers=viewer)
    assert resp.status_code == 403


def test_viewer_can_read_queue(client, make_user):
    """Viewers may still read the approval queue (read-only)."""
    viewer = make_user(role="viewer")
    resp = client.get("/approvals", headers=viewer)
    assert resp.status_code == 200


def test_secondary_caregiver_can_decide(client, make_user, write_audit):
    """A secondary caregiver may reject (RBAC allows both caregiver roles)."""
    secondary = make_user(role="caregiver_secondary")
    action_id = write_audit(action_type="manual_review", outcome="pending")
    resp = client.post(f"/approvals/{action_id}/reject", headers=secondary)
    assert resp.status_code == 200
