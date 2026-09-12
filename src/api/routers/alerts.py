"""Alerts feed and acknowledgement.

- ``GET  /alerts``              — recent family-facing alert events, read from
  the audit trail and filtered to ``{send_alert, send_sms, send_email}``.
- ``POST /alerts/{alert_id}/ack`` — a human acknowledges an alert.

Read-only feed returns 200 regardless of agent-SDK availability. Acknowledging
writes exactly one audit event (actor="human") — mirroring the Supervisor's
reject path, where the human decision is complete in itself.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api import audit_query
from src.api.dependencies import get_current_user, require_roles
from src.api.schemas import ActionResponse, AlertAckRequest, AuditEvent
from src.api.security import ROLE_CAREGIVER_PRIMARY, ROLE_CAREGIVER_SECONDARY
from src.models.audit_log import get_audit_events, write_audit_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])

# Caregivers (not viewers) may acknowledge alerts.
_ack_roles = require_roles(ROLE_CAREGIVER_PRIMARY, ROLE_CAREGIVER_SECONDARY)


@router.get("", response_model=list[AuditEvent])
async def list_alerts(
    care_recipient_id: Optional[str] = Query(default=None),
    _user: dict = Depends(get_current_user),
) -> list[AuditEvent]:
    """Return the recent alerts feed.

    Args:
        care_recipient_id: Optional recipient filter.
        _user: Injected authenticated user.

    Returns:
        Alert ``AuditEvent`` models, newest first.
    """
    return audit_query.fetch_alerts(care_recipient_id=care_recipient_id)


@router.post("/{alert_id}/ack", response_model=ActionResponse)
async def acknowledge_alert(
    alert_id: str,
    body: Optional[AlertAckRequest] = None,
    user: dict = Depends(_ack_roles),
) -> ActionResponse:
    """Acknowledge an alert, recording the human action in the audit trail.

    Args:
        alert_id: The audit ``event_id`` of the alert to acknowledge.
        body: Optional acknowledgement note.
        user: Injected authenticated caregiver.

    Returns:
        ``ActionResponse`` with the acknowledgement correlation id.

    Raises:
        HTTPException: 404 if the alert does not exist or is not an alert event.
    """
    target: Optional[dict] = None
    for row in get_audit_events():
        if row["event_id"] == alert_id:
            target = row
            break

    if target is None or target["action_type"] not in audit_query.ALERT_ACTION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found"
        )

    correlation_id = target.get("correlation_id") or str(uuid4())
    note = body.note if body else None
    note_suffix = f" Note: {note}" if note else ""
    write_audit_event(
        actor="human",
        action_type="acknowledge_alert",
        care_recipient_id=target["care_recipient_id"],
        rationale=f"Caregiver acknowledged alert '{target['action_type']}' ({alert_id}).{note_suffix}",
        outcome="success",
        correlation_id=correlation_id,
        authorization_ref=alert_id,
    )
    logger.info("Alert %s acknowledged by user %s", alert_id, user["user_id"])
    return ActionResponse(
        status="ok",
        detail="Alert acknowledged",
        action_id=alert_id,
        correlation_id=correlation_id,
        acknowledged_at=datetime.now(timezone.utc),
    )
