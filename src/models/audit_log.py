"""Immutable SQLite audit trail for CareBridge.

Every agent action produces exactly one audit event. The "before action"
event (outcome="pending") MUST be written BEFORE executing the action.
Events are append-only: UPDATE and DELETE are blocked by SQLite triggers.
"""

import sqlite3
import logging
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = "audit.db"


def init_audit_db(db_path: str = DB_PATH) -> None:
    """Initialize the audit database with schema and immutability triggers.

    Args:
        db_path: Path to the SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS audit_events (
            event_id        TEXT PRIMARY KEY,
            timestamp       TEXT NOT NULL,
            actor           TEXT NOT NULL,
            action_type     TEXT NOT NULL,
            care_recipient_id TEXT NOT NULL,
            rationale       TEXT NOT NULL,
            outcome         TEXT NOT NULL,
            correlation_id  TEXT NOT NULL,
            authorization_ref TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp);
        CREATE INDEX IF NOT EXISTS idx_audit_correlation ON audit_events(correlation_id);
        CREATE INDEX IF NOT EXISTS idx_audit_recipient ON audit_events(care_recipient_id);
    """)

    # Create triggers - use IF NOT EXISTS pattern via try/except
    try:
        cursor.execute("""
            CREATE TRIGGER prevent_audit_update
            BEFORE UPDATE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'Audit events are immutable');
            END;
        """)
    except sqlite3.OperationalError as e:
        if "already exists" in str(e):
            pass  # Trigger already exists
        else:
            logger.error("Failed to create audit trigger: %s", e)
            raise

    try:
        cursor.execute("""
            CREATE TRIGGER prevent_audit_delete
            BEFORE DELETE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'Audit events are immutable');
            END;
        """)
    except sqlite3.OperationalError as e:
        if "already exists" in str(e):
            pass  # Trigger already exists
        else:
            logger.error("Failed to create audit trigger: %s", e)
            raise

    conn.commit()
    conn.close()


def write_audit_event(
    actor: str,
    action_type: str,
    care_recipient_id: str,
    rationale: str,
    outcome: str,
    correlation_id: str,
    authorization_ref: Optional[str] = None,
    db_path: str = DB_PATH
) -> str:
    """Write an immutable audit event to the database.

    Args:
        actor: One of supervisor, medication, appointment, logistics, communication, human.
        action_type: Tool name (e.g., order_refill, send_alert).
        care_recipient_id: FK to care recipient.
        rationale: Why the agent took this action.
        outcome: success | failure | pending | escalated.
        correlation_id: UUID shared across all actions for the same event.
        authorization_ref: ID of human approval if applicable.
        db_path: Path to the SQLite database file.

    Returns:
        The generated event_id (UUID v4 string).

    Raises:
        sqlite3.Error: If the database write fails.
    """
    event_id = str(uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO audit_events
               (event_id, timestamp, actor, action_type, care_recipient_id,
                rationale, outcome, correlation_id, authorization_ref)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, timestamp, actor, action_type, care_recipient_id,
             rationale, outcome, correlation_id, authorization_ref)
        )
        conn.commit()
        logger.info(f"Audit event {event_id}: {actor}/{action_type} -> {outcome}")
        return event_id
    except Exception as e:
        logger.error(f"Failed to write audit event: {e}")
        raise
    finally:
        conn.close()


def get_audit_events(
    care_recipient_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    db_path: str = DB_PATH
) -> list[dict]:
    """Retrieve audit events with optional filtering.

    Args:
        care_recipient_id: Filter by care recipient.
        correlation_id: Filter by correlation ID.
        db_path: Path to the SQLite database file.

    Returns:
        List of audit event dictionaries.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = "SELECT * FROM audit_events WHERE 1=1"
    params = []

    if care_recipient_id:
        query += " AND care_recipient_id = ?"
        params.append(care_recipient_id)
    if correlation_id:
        query += " AND correlation_id = ?"
        params.append(correlation_id)

    query += " ORDER BY timestamp DESC"
    cursor.execute(query, params)
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results
