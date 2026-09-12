"""SQLite-backed user store for API authentication.

Deliberately separate from the immutable audit trail (``audit.db``): the audit
schema is append-only and off-limits (AGENTS.md §3), and credentials are a
different concern. This store owns a single ``users`` table.

All queries are parameterized (guardrail J). Connections are opened per-call and
closed immediately, which is safe for the API's concurrency profile and avoids
cross-thread SQLite handle sharing. PII policy: we store an email (the login
identity) and an optional display name, but nothing is written to *logs* — logs
carry only ``user_id`` (guardrail J / §10).
"""

import json as _json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from src.api.config import Settings, get_settings

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id           TEXT PRIMARY KEY,
    email             TEXT UNIQUE NOT NULL,
    password_hash     TEXT,
    role              TEXT NOT NULL,
    full_name         TEXT,
    care_recipient_id TEXT,
    firebase_uid      TEXT,
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_firebase_uid
    ON users(firebase_uid) WHERE firebase_uid IS NOT NULL;

CREATE TABLE IF NOT EXISTS medications (
    id TEXT PRIMARY KEY,
    care_recipient_id TEXT NOT NULL,
    name TEXT NOT NULL,
    dosage TEXT NOT NULL,
    frequency TEXT NOT NULL,
    refill_threshold INTEGER NOT NULL DEFAULT 5,
    pharmacy_id TEXT,
    notes TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_meds_care_recipient
    ON medications(care_recipient_id) WHERE active = 1;

CREATE TABLE IF NOT EXISTS appointments (
    id TEXT PRIMARY KEY,
    care_recipient_id TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    specialty TEXT,
    appointment_at TEXT NOT NULL,
    location TEXT,
    prep_required TEXT,
    transportation_needed INTEGER DEFAULT 0,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'scheduled',
    created_at TEXT NOT NULL,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_appts_care_recipient
    ON appointments(care_recipient_id);

CREATE TABLE IF NOT EXISTS care_recipients (
    id TEXT PRIMARY KEY,
    primary_user_id TEXT,
    full_name TEXT NOT NULL DEFAULT 'My Parent',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cr_primary_user
    ON care_recipients(primary_user_id);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id TEXT PRIMARY KEY,
    notification_prefs TEXT NOT NULL,
    escalation_order TEXT NOT NULL,
    quiet_hours_start TEXT,
    quiet_hours_end TEXT,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    language TEXT NOT NULL DEFAULT 'en',
    updated_at TEXT NOT NULL
);
"""


def _resolve_db(db_path: Optional[str]) -> str:
    """Resolve the users DB path, defaulting to ``settings.auth_db_path``."""
    return db_path or get_settings().auth_db_path


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_user_db(db_path: Optional[str] = None) -> None:
    """Create the ``users`` table if it does not exist (idempotent).

    Also migrates older schemas by adding the ``firebase_uid`` column when
    it is missing (ALTER TABLE ADD COLUMN is safe on existing databases).

    Args:
        db_path: Override path; defaults to ``settings.auth_db_path``.
    """
    path = _resolve_db(db_path)
    conn = _connect(path)
    try:
        conn.executescript(_SCHEMA)
        # Migration: add firebase_uid column if missing (for existing auth.db files).
        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN firebase_uid TEXT"
            )
            conn.commit()
            logger.info("Migration: added firebase_uid column to users table")
        except sqlite3.OperationalError:
            pass  # Column already exists.
        # Migration: create the unique index if missing.
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_firebase_uid "
                "ON users(firebase_uid) WHERE firebase_uid IS NOT NULL"
            )
            conn.commit()
        except sqlite3.OperationalError:
            pass
    finally:
        conn.close()


def count_users(db_path: Optional[str] = None) -> int:
    """Return the number of rows in the ``users`` table."""
    path = _resolve_db(db_path)
    conn = _connect(path)
    try:
        cur = conn.execute("SELECT COUNT(*) AS n FROM users")
        row = cur.fetchone()
        return int(row["n"]) if row else 0
    finally:
        conn.close()


def get_user_by_email(email: str, db_path: Optional[str] = None) -> Optional[dict]:
    """Fetch a user by email (case-sensitive match on the stored value)."""
    path = _resolve_db(db_path)
    conn = _connect(path)
    try:
        cur = conn.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_firebase_uid(
    uid: str, db_path: Optional[str] = None
) -> Optional[dict]:
    """Fetch a user by their linked Firebase UID.

    Args:
        uid: The Firebase UID (from the ID token).
        db_path: Override path; defaults to ``settings.auth_db_path``.

    Returns:
        The user dict, or None if no user is linked to that Firebase UID.
    """
    path = _resolve_db(db_path)
    conn = _connect(path)
    try:
        cur = conn.execute(
            "SELECT * FROM users WHERE firebase_uid = ?", (uid,)
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: str, db_path: Optional[str] = None) -> Optional[dict]:
    """Fetch a user by primary key."""
    path = _resolve_db(db_path)
    conn = _connect(path)
    try:
        cur = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_user(
    email: str,
    password_hash: Optional[str],
    role: str,
    full_name: Optional[str] = None,
    care_recipient_id: Optional[str] = None,
    firebase_uid: Optional[str] = None,
    db_path: Optional[str] = None,
) -> dict:
    """Insert a new user and return the stored row.

    Args:
        email: Login identity (unique).
        password_hash: Pre-hashed bcrypt password, or None for Firebase-only users.
        role: RBAC role.
        full_name: Optional display name.
        care_recipient_id: Optional care recipient this user is bound to.
        firebase_uid: Optional Firebase UID to link at creation time.
        db_path: Override path; defaults to ``settings.auth_db_path``.

    Returns:
        The created user as a dict.

    Raises:
        sqlite3.IntegrityError: If the email already exists.
    """
    path = _resolve_db(db_path)
    user_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    conn = _connect(path)
    try:
        conn.execute(
            """INSERT INTO users
               (user_id, email, password_hash, role, full_name,
                care_recipient_id, firebase_uid, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, email, password_hash, role, full_name,
             care_recipient_id, firebase_uid, created_at),
        )
        conn.commit()
        logger.info("Created user %s with role %s", user_id, role)
        return get_user_by_id(user_id, db_path=path) or {}
    finally:
        conn.close()


def seed_demo_user(
    settings: Optional[Settings] = None, db_path: Optional[str] = None
) -> Optional[dict]:
    """Seed the demo user on first startup when the users table is empty.

    Clearly-flagged demo bootstrap (SPEC section C): runs only when
    ``DEMO_MODE=true`` and no users exist. Disabled entirely when
    ``DEMO_MODE=false``.

    Args:
        settings: Optional settings override; defaults to ``get_settings()``.
        db_path: Optional users DB path override.

    Returns:
        The seeded user dict, or None if seeding was skipped.
    """
    settings = settings or get_settings()
    if not settings.demo_mode:
        return None

    init_user_db(db_path)
    if count_users(db_path) > 0:
        return None

    from src.api.security import hash_password, is_valid_role

    role = settings.demo_user_role if is_valid_role(settings.demo_user_role) else "viewer"
    user = create_user(
        email=settings.demo_user_email,
        password_hash=hash_password(settings.demo_user_password),
        role=role,
        full_name="Demo Caregiver",
        care_recipient_id="cr-001",
        db_path=db_path,
    )
    logger.warning(
        "DEMO_MODE bootstrap: seeded demo user %s (role=%s). "
        "Set DEMO_MODE=false in production.",
        user.get("user_id"),
        role,
    )
    return user


def create_user_from_firebase(
    uid: str,
    email: str,
    full_name: Optional[str] = None,
    db_path: Optional[str] = None,
) -> dict:
    """Create a new user linked to a Firebase identity (no password).

    Args:
        uid: Firebase UID.
        email: Email from the Firebase profile.
        full_name: Display name from the Firebase profile.
        db_path: Override path; defaults to ``settings.auth_db_path``.

    Returns:
        The created user dict.
    """
    return create_user(
        email=email,
        password_hash=None,
        role="caregiver_primary",
        full_name=full_name,
        firebase_uid=uid,
        db_path=db_path,
    )


def create_care_recipient_for_user(
    user_id: str,
    full_name: Optional[str] = None,
    db_path: Optional[str] = None,
) -> str:
    """Create a care_recipient row and link it to the user.

    Args:
        user_id: The CareBridge user_id to link.
        full_name: Display name for the care recipient.
        db_path: Override path; defaults to ``settings.auth_db_path``.

    Returns:
        The new care_recipient id.
    """
    path = _resolve_db(db_path)
    cr_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    display_name = full_name or "My Parent"
    conn = _connect(path)
    try:
        conn.execute(
            """INSERT INTO care_recipients
               (id, primary_user_id, full_name, created_at)
               VALUES (?, ?, ?, ?)""",
            (cr_id, user_id, display_name, now),
        )
        conn.execute(
            "UPDATE users SET care_recipient_id = ? WHERE user_id = ?",
            (cr_id, user_id),
        )
        conn.commit()
        logger.info(
            "Created care_recipient %s for user %s", cr_id, user_id,
        )
        return cr_id
    finally:
        conn.close()


def link_firebase_uid(
    user_id: str, uid: str, db_path: Optional[str] = None
) -> None:
    """Link a Firebase UID to an existing user.

    Args:
        user_id: The CareBridge user_id.
        uid: The Firebase UID to link.
        db_path: Override path; defaults to ``settings.auth_db_path``.

    Raises:
        sqlite3.IntegrityError: If the firebase_uid is already linked to another user.
    """
    path = _resolve_db(db_path)
    conn = _connect(path)
    try:
        conn.execute(
            "UPDATE users SET firebase_uid = ? WHERE user_id = ?",
            (uid, user_id),
        )
        conn.commit()
        logger.info("Linked firebase_uid=%s to user_id=%s", uid, user_id)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Medications CRUD helpers
# ---------------------------------------------------------------------------

def create_medication(
    care_recipient_id: str,
    name: str,
    dosage: str,
    frequency: str,
    refill_threshold: int = 5,
    pharmacy_id: Optional[str] = None,
    notes: Optional[str] = None,
    db_path: Optional[str] = None,
) -> dict:
    """Insert a new medication row and return it."""
    path = _resolve_db(db_path)
    med_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect(path)
    try:
        conn.execute(
            """INSERT INTO medications
               (id, care_recipient_id, name, dosage, frequency,
                refill_threshold, pharmacy_id, notes, active, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (med_id, care_recipient_id, name, dosage, frequency,
             refill_threshold, pharmacy_id, notes, now),
        )
        conn.commit()
        return get_medication(med_id, db_path=path) or {}
    finally:
        conn.close()


def list_medications(
    care_recipient_id: str, db_path: Optional[str] = None
) -> list[dict]:
    """Return all active medications for a care recipient."""
    path = _resolve_db(db_path)
    conn = _connect(path)
    try:
        cur = conn.execute(
            "SELECT * FROM medications "
            "WHERE care_recipient_id = ? AND active = 1 "
            "ORDER BY created_at DESC",
            (care_recipient_id,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_medication(
    med_id: str, db_path: Optional[str] = None
) -> Optional[dict]:
    """Fetch a single medication by ID (regardless of active status)."""
    path = _resolve_db(db_path)
    conn = _connect(path)
    try:
        cur = conn.execute(
            "SELECT * FROM medications WHERE id = ?", (med_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_medication(
    med_id: str, updates: dict, db_path: Optional[str] = None
) -> Optional[dict]:
    """Update mutable fields on a medication row. Returns the updated row."""
    path = _resolve_db(db_path)
    allowed = {"name", "dosage", "frequency", "refill_threshold", "pharmacy_id", "notes"}
    fields = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if not fields:
        return get_medication(med_id, db_path=path)
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [med_id]
    conn = _connect(path)
    try:
        conn.execute(
            f"UPDATE medications SET {set_clause} WHERE id = ?", values
        )
        conn.commit()
        return get_medication(med_id, db_path=path)
    finally:
        conn.close()


def soft_delete_medication(
    med_id: str, db_path: Optional[str] = None
) -> Optional[dict]:
    """Soft-delete a medication (active=0). Returns the updated row."""
    path = _resolve_db(db_path)
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect(path)
    try:
        conn.execute(
            "UPDATE medications SET active = 0, updated_at = ? WHERE id = ?",
            (now, med_id),
        )
        conn.commit()
        return get_medication(med_id, db_path=path)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Appointments CRUD helpers
# ---------------------------------------------------------------------------

def create_appointment(
    care_recipient_id: str,
    provider_name: str,
    appointment_at: str,
    specialty: Optional[str] = None,
    location: Optional[str] = None,
    prep_required: Optional[list[str]] = None,
    transportation_needed: bool = False,
    notes: Optional[str] = None,
    db_path: Optional[str] = None,
) -> dict:
    """Insert a new appointment row and return it."""
    path = _resolve_db(db_path)
    appt_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    prep_json = _json.dumps(prep_required or [])
    conn = _connect(path)
    try:
        conn.execute(
            """INSERT INTO appointments
               (id, care_recipient_id, provider_name, specialty, appointment_at,
                location, prep_required, transportation_needed, notes,
                status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled', ?)""",
            (appt_id, care_recipient_id, provider_name, specialty,
             appointment_at, location, prep_json,
             int(transportation_needed), notes, now),
        )
        conn.commit()
        return get_appointment(appt_id, db_path=path) or {}
    finally:
        conn.close()


def list_appointments(
    care_recipient_id: str, db_path: Optional[str] = None
) -> list[dict]:
    """Return all appointments for a care recipient."""
    path = _resolve_db(db_path)
    conn = _connect(path)
    try:
        cur = conn.execute(
            "SELECT * FROM appointments "
            "WHERE care_recipient_id = ? "
            "ORDER BY appointment_at DESC",
            (care_recipient_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        for row in rows:
            row["prep_required"] = _json.loads(row.get("prep_required") or "[]")
            row["transportation_needed"] = bool(row.get("transportation_needed"))
        return rows
    finally:
        conn.close()


def get_appointment(
    appt_id: str, db_path: Optional[str] = None
) -> Optional[dict]:
    """Fetch a single appointment by ID."""
    path = _resolve_db(db_path)
    conn = _connect(path)
    try:
        cur = conn.execute(
            "SELECT * FROM appointments WHERE id = ?", (appt_id,)
        )
        row = cur.fetchone()
        if row:
            d = dict(row)
            d["prep_required"] = _json.loads(d.get("prep_required") or "[]")
            d["transportation_needed"] = bool(d.get("transportation_needed"))
            return d
        return None
    finally:
        conn.close()


def update_appointment(
    appt_id: str, updates: dict, db_path: Optional[str] = None
) -> Optional[dict]:
    """Update mutable fields on an appointment row."""
    path = _resolve_db(db_path)
    allowed = {
        "provider_name", "specialty", "appointment_at", "location",
        "prep_required", "transportation_needed", "notes", "status",
    }
    fields: dict = {}
    for k, v in updates.items():
        if k not in allowed or v is None:
            continue
        if k == "prep_required":
            fields[k] = _json.dumps(v)
        elif k == "transportation_needed":
            fields[k] = int(v)
        else:
            fields[k] = v
    if not fields:
        return get_appointment(appt_id, db_path=path)
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [appt_id]
    conn = _connect(path)
    try:
        conn.execute(
            f"UPDATE appointments SET {set_clause} WHERE id = ?", values
        )
        conn.commit()
        return get_appointment(appt_id, db_path=path)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# User Settings helpers
# ---------------------------------------------------------------------------

_DEFAULT_SETTINGS: dict = {
    "notification_prefs": {"email": True, "sms": True, "push": True},
    "escalation_order": [],
    "timezone": "UTC",
    "language": "en",
}


def get_or_create_settings(
    user_id: str, db_path: Optional[str] = None
) -> dict:
    """Fetch user settings, auto-creating defaults if missing."""
    path = _resolve_db(db_path)
    conn = _connect(path)
    try:
        cur = conn.execute(
            "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
        )
        row = cur.fetchone()
        if row:
            d = dict(row)
            d["notification_prefs"] = _json.loads(d["notification_prefs"])
            d["escalation_order"] = _json.loads(d["escalation_order"])
            return d
        # Auto-create with defaults.
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO user_settings
               (user_id, notification_prefs, escalation_order,
                timezone, language, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id,
             _json.dumps(_DEFAULT_SETTINGS["notification_prefs"]),
             _json.dumps(_DEFAULT_SETTINGS["escalation_order"]),
             _DEFAULT_SETTINGS["timezone"],
             _DEFAULT_SETTINGS["language"],
             now),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
        )
        row = cur.fetchone()
        d = dict(row)
        d["notification_prefs"] = _json.loads(d["notification_prefs"])
        d["escalation_order"] = _json.loads(d["escalation_order"])
        return d
    finally:
        conn.close()


def update_settings(
    user_id: str, updates: dict, db_path: Optional[str] = None
) -> dict:
    """Merge partial updates into user settings."""
    path = _resolve_db(db_path)
    current = get_or_create_settings(user_id, db_path=path)
    now = datetime.now(timezone.utc).isoformat()

    new_prefs = current["notification_prefs"]
    new_order = current["escalation_order"]
    quiet_start = current.get("quiet_hours_start")
    quiet_end = current.get("quiet_hours_end")
    tz = current["timezone"]
    lang = current["language"]

    if "notification_prefs" in updates and updates["notification_prefs"] is not None:
        prefs = updates["notification_prefs"]
        if hasattr(prefs, "model_dump"):
            new_prefs = prefs.model_dump()
        elif isinstance(prefs, dict):
            new_prefs = prefs
    if "escalation_order" in updates and updates["escalation_order"] is not None:
        new_order = updates["escalation_order"]
    if "quiet_hours_start" in updates:
        quiet_start = updates["quiet_hours_start"]
    if "quiet_hours_end" in updates:
        quiet_end = updates["quiet_hours_end"]
    if "timezone" in updates and updates["timezone"] is not None:
        tz = updates["timezone"]
    if "language" in updates and updates["language"] is not None:
        lang = updates["language"]

    conn = _connect(path)
    try:
        conn.execute(
            """UPDATE user_settings SET
               notification_prefs = ?, escalation_order = ?,
               quiet_hours_start = ?, quiet_hours_end = ?,
               timezone = ?, language = ?, updated_at = ?
               WHERE user_id = ?""",
            (_json.dumps(new_prefs), _json.dumps(new_order),
             quiet_start, quiet_end, tz, lang, now, user_id),
        )
        conn.commit()
        return get_or_create_settings(user_id, db_path=path)
    finally:
        conn.close()
