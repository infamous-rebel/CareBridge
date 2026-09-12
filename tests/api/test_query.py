"""Tests for the caregiver Q&A endpoint backed by the Supervisor (SPEC F)."""


def test_query_success(client, auth_headers):
    """A valid question returns a synthesized answer from the Supervisor."""
    resp = client.post(
        "/query",
        json={"care_recipient_id": "cr-001", "question": "How is mom doing today?"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["care_recipient_id"] == "cr-001"
    assert body["question"] == "How is mom doing today?"
    assert body["status"] == "ok"
    assert isinstance(body["answer"], str) and body["answer"]


def test_query_requires_auth(client):
    """/query is protected — no bearer token means 401."""
    resp = client.post(
        "/query", json={"care_recipient_id": "cr-001", "question": "hi"}
    )
    assert resp.status_code == 401


def test_query_validation_error(client, auth_headers):
    """Empty care_recipient_id / question are rejected with 422."""
    resp = client.post(
        "/query",
        json={"care_recipient_id": "", "question": ""},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_query_degraded_when_supervisor_unavailable(client, auth_headers, monkeypatch):
    """If the Supervisor runtime is absent, /query degrades to 503 (SPEC F)."""
    monkeypatch.setattr("src.api.routers.query.get_supervisor", lambda: None)
    resp = client.post(
        "/query",
        json={"care_recipient_id": "cr-001", "question": "status?"},
        headers=auth_headers,
    )
    assert resp.status_code == 503
    assert resp.json()["status"] == "degraded"
