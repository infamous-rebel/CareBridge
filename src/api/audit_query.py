"""Read/query helpers over the immutable audit trail.

Centralizes the audit-read logic used by the ``/audit``, ``/alerts``, and
``/approvals`` routers so each stays thin. This module **reads only** — it never
writes and never alters the audit schema (AGENTS.md §3). Writes go through
``src.models.audit_log.write_audit_event`` or the Supervisor.

Rows are converted to the domain :class:`~src.models.schemas.AuditEvent` /
:class:`~src.models.schemas.PendingAction` models. Filtering beyond
``care_recipient_id`` / ``correlation_id`` (the only filters the audit layer
supports natively) is applied in Python over the already time-descending result.
"""

import logging
from typing import Optional

from src.api.schemas import AuditEvent, PendingAction
from src.models.audit_log import get_audit_events

logger = logging.getLogger(__name__)

# Action types that represent family-facing alerts (SPEC section F).
ALERT_ACTION_TYPES: frozenset[str] = frozenset({"send_alert", "send_sms", "send_email"})

# Human-decision meta events written by the Supervisor / ack flow. These use the
# audit-first "pending" marker for the *decision itself* and must never surface
# as actionable items in the approval queue.
DECISION_ACTION_TYPES: frozenset[str] = frozenset(
    {"approve_action", "reject_action", "acknowledge_alert"}
)

# Decision events that resolve a pending action (their ``authorization_ref``
# points at the original pending action's event_id).
RESOLVING_ACTION_TYPES: frozenset[str] = frozenset({"approve_action", "reject_action"})


def audit_event_from_row(row: dict) -> AuditEvent:
    """Convert a raw audit row (dict) into an :class:`AuditEvent` model.

    Args:
        row: A dict as returned by ``get_audit_events``.

    Returns:
        The validated ``AuditEvent``.
    """
    return AuditEvent(
        event_id=row["event_id"],
        timestamp=row["timestamp"],
        actor=row["actor"],
        action_type=row["action_type"],
        care_recipient_id=row["care_recipient_id"],
        rationale=row["rationale"],
        outcome=row["outcome"],
        correlation_id=row["correlation_id"],
        authorization_ref=row.get("authorization_ref"),
    )


def fetch_events(
    care_recipient_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    actor: Optional[str] = None,
    action_type: Optional[str] = None,
    outcome: Optional[str] = None,
    action_types: Optional[set[str]] = None,
) -> list[AuditEvent]:
    """Fetch audit events with optional filtering, newest first.

    Args:
        care_recipient_id: Native filter — restrict to one recipient.
        correlation_id: Native filter — restrict to one correlation id.
        actor: Post-filter — restrict to one actor.
        action_type: Post-filter — restrict to one action type.
        outcome: Post-filter — restrict to one outcome.
        action_types: Post-filter — restrict to a set of action types.

    Returns:
        A list of ``AuditEvent`` models ordered by timestamp descending.
    """
    rows = get_audit_events(
        care_recipient_id=care_recipient_id, correlation_id=correlation_id
    )
    events: list[AuditEvent] = []
    for row in rows:
        if actor and row["actor"] != actor:
            continue
        if action_type and row["action_type"] != action_type:
            continue
        if outcome and row["outcome"] != outcome:
            continue
        if action_types and row["action_type"] not in action_types:
            continue
        try:
            events.append(audit_event_from_row(row))
        except (KeyError, ValueError) as exc:
            # The audit trail is immutable (DELETE is trigger-blocked), so a
            # malformed historical row cannot be cleaned up. Skip + log it rather
            # than 500 the whole feed — mirrors synthesize_status' parsing. A
            # pydantic ValidationError is a subclass of ValueError.
            logger.warning(
                "Skipping malformed audit row %s: %s", row.get("event_id", "?"), exc
            )
    return events


def fetch_alerts(care_recipient_id: Optional[str] = None) -> list[AuditEvent]:
    """Fetch family-facing alert events (send_alert / send_sms / send_email).

    Args:
        care_recipient_id: Optional recipient filter.

    Returns:
        Alert ``AuditEvent`` models, newest first.
    """
    return fetch_events(
        care_recipient_id=care_recipient_id, action_types=set(ALERT_ACTION_TYPES)
    )


def fetch_pending_actions(care_recipient_id: Optional[str] = None) -> list[PendingAction]:
    """Build the pending-approval queue from unresolved audit rows.

    A row is an actionable pending item when ``outcome == "pending"``, it is not
    a human-decision meta event, and no later ``approve_action``/``reject_action``
    event references it via ``authorization_ref`` (the audit trail is immutable,
    so resolution is detected by cross-reference rather than by mutating the row).

    Args:
        care_recipient_id: Optional recipient filter.

    Returns:
        ``PendingAction`` models for every unresolved pending entry, newest first.
    """
    rows = get_audit_events(care_recipient_id=care_recipient_id)
    resolved_ids = {
        row["authorization_ref"]
        for row in rows
        if row["action_type"] in RESOLVING_ACTION_TYPES and row.get("authorization_ref")
    }
    actions: list[PendingAction] = []
    for row in rows:
        if row["outcome"] != "pending":
            continue
        if row["action_type"] in DECISION_ACTION_TYPES:
            continue
        if row["event_id"] in resolved_ids:
            continue
        try:
            actions.append(
                PendingAction(
                    action_id=row["event_id"],
                    action_type=row["action_type"],
                    care_recipient_id=row["care_recipient_id"],
                    rationale=row["rationale"],
                    requested_at=row["timestamp"],
                    status="pending",
                    authorization_ref=row.get("authorization_ref"),
                )
            )
        except (KeyError, ValueError) as exc:
            # Skip malformed immutable rows rather than 500 the queue (see above).
            logger.warning(
                "Skipping malformed pending audit row %s: %s",
                row.get("event_id", "?"),
                exc,
            )
    return actions


def paginate(items: list, page: int, page_size: int) -> tuple[list, int, int]:
    """Paginate a list.

    Args:
        items: The full ordered list.
        page: 1-based page number.
        page_size: Items per page (>= 1).

    Returns:
        ``(page_items, total, pages)`` where ``pages`` is at least 1.
    """
    total = len(items)
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(max(1, page), pages)
    start = (page - 1) * page_size
    return items[start : start + page_size], total, pages
