"""Appointment listing for a care recipient (read-only).

``GET /appointments/{care_recipient_id}`` returns upcoming appointments via the
deterministic ``get_calendar`` tool (an AUTO-category action — no external API).
Read-only: the API never schedules or cancels appointments (AGENTS.md §1).
"""

import logging

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_current_user
from src.api.schemas import Appointment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("/{care_recipient_id}", response_model=list[Appointment])
async def list_appointments(
    care_recipient_id: str,
    horizon_days: int = Query(default=30, ge=1, le=365),
    _user: dict = Depends(get_current_user),
) -> list[Appointment]:
    """Return upcoming appointments for a care recipient.

    Args:
        care_recipient_id: The recipient whose calendar to read.
        horizon_days: How many days ahead to include (1..365).
        _user: Injected authenticated user.

    Returns:
        A list of ``Appointment`` models within the horizon.
    """
    from src.tools.appointment_tools import get_calendar

    appts = get_calendar(care_recipient_id, horizon_days=horizon_days)
    logger.info(
        "Listed %d appointment(s) for recipient %s", len(appts), care_recipient_id
    )
    return appts
