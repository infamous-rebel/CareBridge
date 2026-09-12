"""Tests for appointments CRUD endpoints."""

from datetime import datetime, timedelta, timezone


def _future_iso(days: int = 7) -> str:
    """Return an ISO 8601 datetime string `days` in the future."""
    dt = datetime.now(timezone.utc) + timedelta(days=days)
    return dt.isoformat()


def _appt_payload(**overrides):
    base = {
        "provider_name": "Dr. Smith",
        "appointment_at": _future_iso(),
    }
    base.update(overrides)
    return base


# -- create ------------------------------------------------------------------

def test_create_appointment(client, auth_headers):
    """POST creates an appointment and returns 201."""
    resp = client.post(
        "/care-recipients/me/appointments",
        json=_appt_payload(),
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["provider_name"] == "Dr. Smith"
    assert body["status"] == "scheduled"
    assert body["transportation_needed"] is False
    assert body["prep_required"] == []
    assert body["id"]


def test_create_appointment_requires_auth(client):
    """POST without bearer token is 401."""
    resp = client.post(
        "/care-recipients/me/appointments", json=_appt_payload()
    )
    assert resp.status_code == 401


def test_create_appointment_past_date_rejected(client, auth_headers):
    """An appointment_at in the past is rejected with 422."""
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    resp = client.post(
        "/care-recipients/me/appointments",
        json=_appt_payload(appointment_at=past),
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_create_appointment_with_prep(client, auth_headers):
    """prep_required is stored as a list."""
    resp = client.post(
        "/care-recipients/me/appointments",
        json=_appt_payload(prep_required=["Fast 12hrs", "Bring ID"]),
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["prep_required"] == ["Fast 12hrs", "Bring ID"]


# -- read --------------------------------------------------------------------

def test_get_appointment(client, auth_headers):
    """GET /{id} returns the appointment."""
    create = client.post(
        "/care-recipients/me/appointments",
        json=_appt_payload(),
        headers=auth_headers,
    )
    appt_id = create.json()["id"]
    resp = client.get(
        f"/care-recipients/me/appointments/{appt_id}", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["provider_name"] == "Dr. Smith"


def test_get_appointment_not_found(client, auth_headers):
    """GET /{id} with unknown ID is 404."""
    resp = client.get(
        "/care-recipients/me/appointments/nonexistent-uuid",
        headers=auth_headers,
    )
    assert resp.status_code == 404


# -- list --------------------------------------------------------------------

def test_list_appointments(client, auth_headers):
    """GET / returns all appointments for the care recipient."""
    client.post(
        "/care-recipients/me/appointments",
        json=_appt_payload(provider_name="Dr. A"),
        headers=auth_headers,
    )
    client.post(
        "/care-recipients/me/appointments",
        json=_appt_payload(provider_name="Dr. B"),
        headers=auth_headers,
    )
    resp = client.get(
        "/care-recipients/me/appointments", headers=auth_headers
    )
    assert resp.status_code == 200
    names = [a["provider_name"] for a in resp.json()]
    assert "Dr. A" in names
    assert "Dr. B" in names


# -- update ------------------------------------------------------------------

def test_update_appointment(client, auth_headers):
    """PUT /{id} updates the appointment."""
    create = client.post(
        "/care-recipients/me/appointments",
        json=_appt_payload(),
        headers=auth_headers,
    )
    appt_id = create.json()["id"]
    resp = client.put(
        f"/care-recipients/me/appointments/{appt_id}",
        json={"location": "Room 42"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["location"] == "Room 42"
    assert resp.json()["provider_name"] == "Dr. Smith"  # unchanged


# -- cancel ------------------------------------------------------------------

def test_cancel_appointment(client, auth_headers):
    """POST /{id}/cancel sets status to cancelled."""
    create = client.post(
        "/care-recipients/me/appointments",
        json=_appt_payload(),
        headers=auth_headers,
    )
    appt_id = create.json()["id"]
    resp = client.post(
        f"/care-recipients/me/appointments/{appt_id}/cancel",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


# -- ownership isolation -----------------------------------------------------

def test_appointment_ownership_isolation(client, make_user):
    """User B cannot see User A's appointment (different care_recipient_id)."""
    user_a = make_user(role="caregiver_primary", care_recipient_id="cr-001")
    user_b = make_user(role="caregiver_primary", care_recipient_id="cr-002")

    create = client.post(
        "/care-recipients/me/appointments",
        json=_appt_payload(),
        headers=user_a,
    )
    appt_id = create.json()["id"]

    resp = client.get(
        f"/care-recipients/me/appointments/{appt_id}", headers=user_b
    )
    assert resp.status_code == 404
