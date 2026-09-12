"""Approval queue and human decision endpoints.

- ``GET  /approvals``                  — pending actions (audit rows with
  ``outcome="pending"``) as a ``PendingAction`` queue.
- ``POST /approvals/{action_id}/approve`` — ``Supervisor.approve_pending_action(id, True)``.
- ``POST /approvals/{action_id}/reject``  — ``Supervisor.approve_pending_action(id, False)``.

Decisions are restricted to caregiver roles (viewers may only read the queue).
The Supervisor writes the authoritative audit entries (audit-first); the optional
``reason`` is logged server-side for operator context and never contains PII.

Graceful degradation (SPEC section F): if the Supervisor is unavailable, the
decision endpoints return HTTP 503 with ``{"status": "degraded", "reason": ...}``
while the read-only queue still returns 200.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from src.api import audit_query
from src.api.dependencies import get_current_user, get_supervisor, require_roles
from src.api.schemas import ActionResponse, ApprovalDecision, DegradedResponse, PendingAction
from src.api.security import ROLE_CAREGIVER_PRIMARY, ROLE_CAREGIVER_SECONDARY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])

# Only caregivers may approve/reject; viewers get 403 via require_roles.
_decision_roles = require_roles(ROLE_CAREGIVER_PRIMARY, ROLE_CAREGIVER_SECONDARY)


@router.get("", response_model=list[PendingAction])
async def list_approvals(
    care_recipient_id: Optional[str] = Query(default=None),
    _user: dict = Depends(get_current_user),
) -> list[PendingAction]:
    """Return the pending-approval queue.

    Args:
        care_recipient_id: Optional recipient filter.
        _user: Injected authenticated user.

    Returns:
        ``PendingAction`` models for every unresolved audit entry, newest first.
    """
    return audit_query.fetch_pending_actions(care_recipient_id=care_recipient_id)


async def _decide(action_id: str, approved: bool, reason: Optional[str], user: dict):
    """Shared approve/reject implementation.

    Args:
        action_id: Pending action (audit event_id).
        approved: True to approve, False to reject.
        reason: Optional operator reason (logged, not sent to any third party).
        user: Injected authenticated caregiver.

    Returns:
        ``ActionResponse`` on success, or a 503 ``JSONResponse`` when degraded.

    Raises:
        HTTPException: 404 if the action is unknown, not pending, or resolved.
    """
    supervisor = get_supervisor()
    if supervisor is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=DegradedResponse(
                reason="Supervisor agent runtime unavailable"
            ).model_dump(),
        )

    verb = "approved" if approved else "rejected"
    try:
        await supervisor.approve_pending_action(action_id, approved)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    logger.info(
        "Pending action %s %s by user %s%s",
        action_id,
        verb,
        user["user_id"],
        f" (reason logged)" if reason else "",
    )
    return ActionResponse(
        status="ok",
        detail=f"Action {verb}",
        action_id=action_id,
    )


@router.post("/{action_id}/approve", response_model=ActionResponse)
async def approve_action(
    action_id: str,
    body: Optional[ApprovalDecision] = None,
    user: dict = Depends(_decision_roles),
) -> ActionResponse:
    """Approve a pending action via the Supervisor.

    Args:
        action_id: Pending action (audit event_id).
        body: Optional decision reason.
        user: Injected authenticated caregiver.

    Returns:
        ``ActionResponse`` (or 503 degraded when the Supervisor is unavailable).
    """
    return await _decide(action_id, True, body.reason if body else None, user)


@router.post("/{action_id}/reject", response_model=ActionResponse)
async def reject_action(
    action_id: str,
    body: Optional[ApprovalDecision] = None,
    user: dict = Depends(_decision_roles),
) -> ActionResponse:
    """Reject a pending action via the Supervisor.

    Args:
        action_id: Pending action (audit event_id).
        body: Optional decision reason.
        user: Injected authenticated caregiver.

    Returns:
        ``ActionResponse`` (or 503 degraded when the Supervisor is unavailable).
    """
    return await _decide(action_id, False, body.reason if body else None, user)
