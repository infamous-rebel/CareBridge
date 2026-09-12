"""Tests for user settings CRUD endpoints."""


# -- get defaults ------------------------------------------------------------

def test_get_settings_defaults(client, auth_headers):
    """GET /settings/me returns defaults on first access."""
    resp = client.get("/settings/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["notification_prefs"] == {"email": True, "sms": True, "push": True}
    assert body["escalation_order"] == []
    assert body["timezone"] == "UTC"
    assert body["language"] == "en"
    assert body["quiet_hours_start"] is None
    assert body["quiet_hours_end"] is None


def test_get_settings_requires_auth(client):
    """GET /settings/me without bearer token is 401."""
    resp = client.get("/settings/me")
    assert resp.status_code == 401


# -- update ------------------------------------------------------------------

def test_update_settings_partial(client, auth_headers):
    """PUT /settings/me accepts partial updates."""
    resp = client.put(
        "/settings/me",
        json={"timezone": "America/New_York", "language": "es"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["timezone"] == "America/New_York"
    assert body["language"] == "es"
    # Unchanged defaults.
    assert body["notification_prefs"]["email"] is True


def test_update_notification_prefs(client, auth_headers):
    """PUT /settings/me updates nested notification_prefs."""
    resp = client.put(
        "/settings/me",
        json={"notification_prefs": {"email": False, "sms": True, "push": False}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["notification_prefs"]["email"] is False
    assert body["notification_prefs"]["push"] is False


def test_update_quiet_hours(client, auth_headers):
    """PUT /settings/me updates quiet hours."""
    resp = client.put(
        "/settings/me",
        json={"quiet_hours_start": "22:00", "quiet_hours_end": "07:00"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["quiet_hours_start"] == "22:00"
    assert body["quiet_hours_end"] == "07:00"


def test_update_escalation_order(client, auth_headers):
    """PUT /settings/me updates escalation_order."""
    resp = client.put(
        "/settings/me",
        json={"escalation_order": ["user-1", "user-2"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["escalation_order"] == ["user-1", "user-2"]


# -- validation --------------------------------------------------------------

def test_invalid_timezone_rejected(client, auth_headers):
    """An invalid IANA timezone is rejected."""
    resp = client.put(
        "/settings/me",
        json={"timezone": "Not/A/Timezone"},
        headers=auth_headers,
    )
    # Either 422 (Pydantic validation) or 422 (manual check in router).
    assert resp.status_code == 422


def test_invalid_quiet_hours_format(client, auth_headers):
    """Quiet hours must be HH:MM format."""
    resp = client.put(
        "/settings/me",
        json={"quiet_hours_start": "not-a-time"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_escalation_order_max_5(client, auth_headers):
    """Escalation order accepts at most 5 entries."""
    resp = client.put(
        "/settings/me",
        json={"escalation_order": ["u1", "u2", "u3", "u4", "u5", "u6"]},
        headers=auth_headers,
    )
    assert resp.status_code == 422


# -- audit trail -------------------------------------------------------------

def test_update_settings_writes_audit(client, auth_headers, temp_audit_db):
    """Updating settings writes audit events."""
    import sqlite3

    client.put(
        "/settings/me",
        json={"language": "bn"},
        headers=auth_headers,
    )
    conn = sqlite3.connect(temp_audit_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT action_type, outcome FROM audit_events "
        "WHERE action_type = 'update_settings' "
        "ORDER BY timestamp"
    ).fetchall()
    conn.close()
    assert len(rows) >= 2
    assert rows[0]["outcome"] == "pending"
    assert rows[-1]["outcome"] == "success"
