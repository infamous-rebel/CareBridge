"""CRUD endpoints for user settings (dashboard operational layer).

Prefix: ``/settings``

``GET /me`` auto-creates default settings on first access.
``PUT /me`` accepts partial updates.

Every mutation writes an audit event BEFORE the DB commit.
Every endpoint requires JWT auth.
"""

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from src.api import user_store
from src.api.dependencies import get_current_user
from src.api.schemas import SettingsOut, SettingsUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


def _row_to_out(row: dict) -> SettingsOut:
    return SettingsOut(
        user_id=row["user_id"],
        notification_prefs=row["notification_prefs"],
        escalation_order=row["escalation_order"],
        quiet_hours_start=row.get("quiet_hours_start"),
        quiet_hours_end=row.get("quiet_hours_end"),
        timezone=row["timezone"],
        language=row["language"],
        updated_at=row["updated_at"],
    )


@router.get("/me", response_model=SettingsOut)
async def get_settings(user: dict = Depends(get_current_user)) -> SettingsOut:
    """Get (or auto-create) settings for the current user.

    Args:
        user: Injected authenticated user.

    Returns:
        The user's settings (defaults on first access).
    """
    row = user_store.get_or_create_settings(user["user_id"])
    return _row_to_out(row)


@router.put("/me", response_model=SettingsOut)
async def update_settings(
    body: SettingsUpdate, user: dict = Depends(get_current_user)
) -> SettingsOut:
    """Partially update the current user's settings.

    Args:
        body: Fields to update (all optional).
        user: Injected authenticated user.

    Returns:
        The updated settings.

    Raises:
        HTTPException: 422 if timezone is not a valid IANA zone.
    """
    # Validate timezone if provided.
    if body.timezone is not None:
        try:
            from zoneinfo import available_timezones

            if body.timezone not in available_timezones():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Unknown timezone: {body.timezone}",
                )
        except ImportError:
            pass  # zoneinfo unavailable; accept any string

    corr_id = str(uuid4())
    from src.models.audit_log import write_audit_event

    crid = user.get("care_recipient_id") or "unassigned"

    write_audit_event(
        actor="human",
        action_type="update_settings",
        care_recipient_id=crid,
        rationale=f"Update settings for user_id={user['user_id']}",
        outcome="pending",
        correlation_id=corr_id,
    )

    updates = body.model_dump(exclude_unset=True)
    row = user_store.update_settings(user["user_id"], updates)

    write_audit_event(
        actor="human",
        action_type="update_settings",
        care_recipient_id=crid,
        rationale=f"Updated settings for user_id={user['user_id']}",
        outcome="success",
        correlation_id=corr_id,
    )
    logger.info("Updated settings for user_id=%s", user["user_id"])
    return _row_to_out(row)
