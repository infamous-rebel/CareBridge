"""Tests for medications CRUD endpoints."""

import pytest


def _med_payload(**overrides):
    base = {"name": "Lisinopril", "dosage": "10mg", "frequency": "daily"}
    base.update(overrides)
    return base


# -- create ------------------------------------------------------------------

def test_create_medication(client, auth_headers):
    """POST creates a medication and returns 201."""
    resp = client.post(
        "/care-recipients/me/medications",
        json=_med_payload(),
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Lisinopril"
    assert body["dosage"] == "10mg"
    assert body["frequency"] == "daily"
    assert body["refill_threshold"] == 5
    assert body["active"] is True
    assert body["id"]


def test_create_medication_requires_auth(client):
    """POST without bearer token is 401."""
    resp = client.post(
        "/care-recipients/me/medications", json=_med_payload()
    )
    assert resp.status_code == 401


def test_create_medication_validation(client, auth_headers):
    """Empty name is rejected with 422."""
    resp = client.post(
        "/care-recipients/me/medications",
        json={"name": "", "dosage": "10mg", "frequency": "daily"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


# -- read --------------------------------------------------------------------

def test_get_medication(client, auth_headers):
    """GET /{id} returns the medication."""
    create = client.post(
        "/care-recipients/me/medications",
        json=_med_payload(),
        headers=auth_headers,
    )
    med_id = create.json()["id"]
    resp = client.get(
        f"/care-recipients/me/medications/{med_id}", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Lisinopril"


def test_get_medication_not_found(client, auth_headers):
    """GET /{id} with unknown ID is 404."""
    resp = client.get(
        "/care-recipients/me/medications/nonexistent-uuid",
        headers=auth_headers,
    )
    assert resp.status_code == 404


# -- list --------------------------------------------------------------------

def test_list_medications(client, auth_headers):
    """GET / returns all active medications."""
    client.post(
        "/care-recipients/me/medications",
        json=_med_payload(name="Med A"),
        headers=auth_headers,
    )
    client.post(
        "/care-recipients/me/medications",
        json=_med_payload(name="Med B"),
        headers=auth_headers,
    )
    resp = client.get("/care-recipients/me/medications", headers=auth_headers)
    assert resp.status_code == 200
    names = [m["name"] for m in resp.json()]
    assert "Med A" in names
    assert "Med B" in names


# -- update ------------------------------------------------------------------

def test_update_medication(client, auth_headers):
    """PUT /{id} updates the medication."""
    create = client.post(
        "/care-recipients/me/medications",
        json=_med_payload(),
        headers=auth_headers,
    )
    med_id = create.json()["id"]
    resp = client.put(
        f"/care-recipients/me/medications/{med_id}",
        json={"dosage": "20mg"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["dosage"] == "20mg"
    assert resp.json()["name"] == "Lisinopril"  # unchanged


# -- delete (soft) -----------------------------------------------------------

def test_delete_medication_soft(client, auth_headers):
    """DELETE /{id} sets active=false and the item disappears from list."""
    create = client.post(
        "/care-recipients/me/medications",
        json=_med_payload(),
        headers=auth_headers,
    )
    med_id = create.json()["id"]
    resp = client.delete(
        f"/care-recipients/me/medications/{med_id}", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["active"] is False

    # Should not appear in the active list.
    list_resp = client.get(
        "/care-recipients/me/medications", headers=auth_headers
    )
    ids = [m["id"] for m in list_resp.json()]
    assert med_id not in ids


# -- ownership isolation -----------------------------------------------------

def test_medication_ownership_isolation(client, make_user):
    """User B cannot see User A's medication (different care_recipient_id)."""
    user_a = make_user(role="caregiver_primary", care_recipient_id="cr-001")
    user_b = make_user(role="caregiver_primary", care_recipient_id="cr-002")

    create = client.post(
        "/care-recipients/me/medications",
        json=_med_payload(),
        headers=user_a,
    )
    med_id = create.json()["id"]

    resp = client.get(
        f"/care-recipients/me/medications/{med_id}", headers=user_b
    )
    assert resp.status_code == 404


# -- audit trail -------------------------------------------------------------

def test_create_medication_writes_audit(client, auth_headers, temp_audit_db):
    """Creating a medication writes audit events."""
    import sqlite3

    client.post(
        "/care-recipients/me/medications",
        json=_med_payload(),
        headers=auth_headers,
    )
    conn = sqlite3.connect(temp_audit_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT action_type, outcome FROM audit_events "
        "WHERE action_type = 'create_medication' "
        "ORDER BY timestamp"
    ).fetchall()
    conn.close()
    assert len(rows) >= 2  # pending + success
    assert rows[0]["outcome"] == "pending"
    assert rows[-1]["outcome"] == "success"
