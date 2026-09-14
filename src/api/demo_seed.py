"""Seed realistic demo audit events on startup.

Writes a realistic week of audit events for care recipient ``cr-001`` when the
trail is empty and ``DEMO_MODE`` is enabled.  Idempotent — checks for a marker
event (``action_type='demo_seed_complete'``) before running so repeated restarts
never duplicate data.
"""

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.models.audit_log import DB_PATH

logger = logging.getLogger(__name__)

# ── Realistic event catalogue ────────────────────────────────────────────────
# Each tuple: (day_offset, hour_offset, actor, action_type, rationale, outcome)
# day_offset is relative to "now" (0 = today, negative = days ago).
# hour_offset fine-tunes ordering within the same day (most recent first).

_SEED_EVENTS: list[tuple[int, int, str, str, str, str]] = [
    # Day 0 — today (most recent first)
    (0,   0, "medication",  "order_refill",
     "Metformin refill placed at CVS #4192", "success"),
    (0,  -1, "medication",  "check_refill_status",
     "Lisinopril — 8 days remaining", "success"),
    (0,  -2, "supervisor",  "synthesize_status",
     "Daily status summary — all systems nominal", "success"),
    (0,  -3, "human",       "login_firebase",
     "Caregiver signed in via Google", "success"),
    # Day -1
    (-1,  0, "appointment", "schedule_appointment",
     "Endocrinology follow-up scheduled for Wed 8:30 PM", "success"),
    (-1, -1, "logistics",   "check_delivery_status",
     "Atorvastatin delivery in transit — ETA tomorrow", "success"),
    (-1, -2, "communication", "send_alert",
     "Refill confirmed — ETA tomorrow", "success"),
    # Day -2
    (-2,  0, "medication",  "detect_adherence_pattern",
     "Evening dose taken 1 hour late — mild deviation", "success"),
    (-2, -1, "communication", "send_alert",
     "Vitals: BP 138/88, mild elevation", "escalated"),
    # Day -3
    (-3,  0, "supervisor",  "synthesize_status",
     "Daily status summary generated", "success"),
    # Day -4
    (-4,  0, "logistics",   "check_delivery_status",
     "Refill in transit — expected delivery tomorrow", "success"),
    # Day -5
    (-5,  0, "medication",  "check_refill_status",
     "Lisinopril refill check — days_remaining=8", "success"),
    # Day -6
    (-6,  0, "communication", "send_alert",
     "Daily digest delivered", "success"),
]

# Pending approval events (outcome='pending')
_PENDING_APPROVALS: list[tuple[str, str, str]] = [
    ("supervisor", "process_event",
     "Routing refill_low event — awaiting caregiver approval"),
    ("supervisor", "process_event",
     "Proposed appointment reschedule — awaiting caregiver approval"),
]

_CARE_RECIPIENT_ID = "cr-001"


def _insert_event(
    db_path: str,
    *,
    actor: str,
    action_type: str,
    rationale: str,
    outcome: str,
    timestamp: str,
    correlation_id: str | None = None,
    authorization_ref: str | None = None,
) -> str:
    """Insert a single audit event with an explicit timestamp.

    Mirrors the schema written by ``write_audit_event()`` but accepts a custom
    timestamp so seed data can be backdated.  Does NOT modify ``audit_log.py``.

    Args:
        db_path: Path to the SQLite audit database.
        actor: Agent actor name.
        action_type: Tool / action name.
        rationale: Human-readable reason for the action.
        outcome: One of success, failure, pending, escalated.
        timestamp: ISO 8601 UTC timestamp string.
        correlation_id: Optional correlation UUID (generated if omitted).
        authorization_ref: Optional approval reference.

    Returns:
        The generated event_id.
    """
    event_id = str(uuid4())
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO audit_events
               (event_id, timestamp, actor, action_type, care_recipient_id,
                rationale, outcome, correlation_id, authorization_ref)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, timestamp, actor, action_type, _CARE_RECIPIENT_ID,
             rationale, outcome, correlation_id or str(uuid4()),
             authorization_ref),
        )
        conn.commit()
    finally:
        conn.close()
    return event_id


def seed_demo_audit_events(db_path: str | None = None) -> None:
    """Write a realistic week of audit events for cr-001 if the trail is empty.

    Idempotent — checks for a marker event (``action_type='demo_seed_complete'``)
    before running.  Only executes when ``settings.DEMO_MODE`` is ``True``.

    Args:
        db_path: Override for the audit database path.  Defaults to the module
            constant from ``src.models.audit_log`` (which the test suite patches
            to a temp file).
    """
    # Lazy import avoids circular dependencies at module load time and ensures
    # we pick up the patched DB_PATH during tests.
    from src.api.config import get_settings

    settings = get_settings()
    if not settings.demo_mode or settings.environment == "test":
        return

    resolved_db = db_path or DB_PATH

    # ── Idempotency guard ────────────────────────────────────────────────
    conn = sqlite3.connect(resolved_db)
    try:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM audit_events "
            "WHERE care_recipient_id = ? AND action_type = 'demo_seed_complete'",
            (_CARE_RECIPIENT_ID,),
        )
        if cursor.fetchone()[0] > 0:
            logger.debug("Demo audit events already seeded — skipping")
            return
    finally:
        conn.close()

    # ── Write backdated events ───────────────────────────────────────────
    now = datetime.now(timezone.utc)
    correlation_root = str(uuid4())

    for day_offset, hour_offset, actor, action_type, rationale, outcome in _SEED_EVENTS:
        ts = (now + timedelta(days=day_offset, hours=hour_offset)).isoformat()
        _insert_event(
            resolved_db,
            actor=actor,
            action_type=action_type,
            rationale=rationale,
            outcome=outcome,
            timestamp=ts,
            correlation_id=correlation_root,
        )

    # ── Pending approval events ──────────────────────────────────────────
    # Timestamped at Day -1 so Day 0 seed events remain the most recent.
    pending_ts = (now - timedelta(days=1)).isoformat()
    for actor, action_type, rationale in _PENDING_APPROVALS:
        _insert_event(
            resolved_db,
            actor=actor,
            action_type=action_type,
            rationale=rationale,
            outcome="pending",
            timestamp=pending_ts,
            correlation_id=correlation_root,
        )

    # ── Marker event (prevents re-seeding) ───────────────────────────────
    _insert_event(
        resolved_db,
        actor="supervisor",
        action_type="demo_seed_complete",
        rationale="Demo audit trail seeded",
        outcome="success",
        timestamp=pending_ts,
        correlation_id=correlation_root,
    )

    logger.info(
        "Seeded %d demo audit events for care_recipient=%s",
        len(_SEED_EVENTS) + len(_PENDING_APPROVALS) + 1,
        _CARE_RECIPIENT_ID,
    )
