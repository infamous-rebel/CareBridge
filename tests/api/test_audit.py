"""Tests for paginated, filterable audit reads (SPEC F).

The audit DB is a per-test temp file (root ``conftest.temp_audit_db``) and only
the events written here populate it — startup, login, and reads never write audit
events — so ``total`` counts are exact.
"""


def test_audit_requires_auth(client):
    """/audit is protected — no bearer token means 401."""
    assert client.get("/audit").status_code == 401


def test_audit_pagination(client, auth_headers, write_audit):
    """page/page_size slice the results and report accurate metadata."""
    for _ in range(5):
        write_audit(action_type="order_refill", outcome="success")

    resp = client.get("/audit?page=1&page_size=2", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["pages"] == 3
    assert len(body["items"]) == 2


def test_audit_second_page(client, auth_headers, write_audit):
    """The second page returns the next slice, not a repeat of the first."""
    for _ in range(5):
        write_audit(action_type="order_refill", outcome="success")

    page1 = client.get("/audit?page=1&page_size=2", headers=auth_headers).json()
    page2 = client.get("/audit?page=2&page_size=2", headers=auth_headers).json()
    ids1 = {i["event_id"] for i in page1["items"]}
    ids2 = {i["event_id"] for i in page2["items"]}
    assert ids1.isdisjoint(ids2)
    assert page2["page"] == 2


def test_audit_filter_by_outcome(client, auth_headers, write_audit):
    """outcome= filters to matching events only."""
    write_audit(action_type="order_refill", outcome="success")
    write_audit(action_type="manual_review", outcome="pending")

    resp = client.get("/audit?outcome=pending", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["outcome"] == "pending"


def test_audit_filter_by_action_type(client, auth_headers, write_audit):
    """action_type= filters to matching events only."""
    write_audit(action_type="order_refill", outcome="success")
    write_audit(action_type="order_refill", outcome="success")
    write_audit(action_type="manual_review", outcome="pending")

    resp = client.get("/audit?action_type=order_refill", headers=auth_headers)
    body = resp.json()
    assert body["total"] == 2
    assert all(i["action_type"] == "order_refill" for i in body["items"])


def test_audit_filter_by_care_recipient(client, auth_headers, write_audit):
    """care_recipient_id= uses the audit layer's native filter."""
    write_audit(care_recipient_id="cr-001", outcome="success")
    write_audit(care_recipient_id="cr-999", outcome="success")

    resp = client.get("/audit?care_recipient_id=cr-999", headers=auth_headers)
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["care_recipient_id"] == "cr-999"


def test_audit_invalid_page_size_is_422(client, auth_headers):
    """page_size below the ge=1 bound is rejected with 422."""
    resp = client.get("/audit?page_size=0", headers=auth_headers)
    assert resp.status_code == 422


def test_audit_skips_malformed_immutable_rows(
    client, auth_headers, write_audit, temp_audit_db
):
    """A malformed row (which cannot be deleted from the immutable trail) is
    skipped and logged, not turned into a 500 for the whole feed."""
    import sqlite3

    write_audit(action_type="order_refill", outcome="success")  # one valid row

    # Insert a row that violates the AuditEvent Literal/UUID constraints
    # (actor='test', correlation_id='c1') directly into the patched temp DB.
    conn = sqlite3.connect(temp_audit_db)
    conn.execute(
        """INSERT INTO audit_events
           (event_id, timestamp, actor, action_type, care_recipient_id,
            rationale, outcome, correlation_id, authorization_ref)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("bad-row-1", "2026-01-01T00:00:00+00:00", "test", "junk",
         "cr-001", "malformed historical row", "success", "c1", None),
    )
    conn.commit()
    conn.close()

    resp = client.get("/audit", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1  # only the valid row survives validation
    assert all(item["actor"] != "test" for item in body["items"])

