"""Delivery listing for a care recipient (read-only).

``GET /deliveries/{care_recipient_id}`` returns delivery records from the fixture
history as domain :class:`~src.models.schemas.DeliveryStatus` models. Read-only:
the API never places or modifies deliveries (AGENTS.md §1).
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends

from src.api.dependencies import get_current_user
from src.api.schemas import DeliveryStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/deliveries", tags=["deliveries"])

FIXTURES_PATH = Path(__file__).resolve().parents[3] / "fixtures"


@router.get("/{care_recipient_id}", response_model=list[DeliveryStatus])
async def list_deliveries(
    care_recipient_id: str, _user: dict = Depends(get_current_user)
) -> list[DeliveryStatus]:
    """Return all deliveries for a care recipient.

    Args:
        care_recipient_id: The recipient whose delivery history to read.
        _user: Injected authenticated user.

    Returns:
        A list of ``DeliveryStatus`` models (empty if none match).
    """
    with open(FIXTURES_PATH / "delivery_history.json") as f:
        rows = json.load(f)
    deliveries = [
        DeliveryStatus(**row)
        for row in rows
        if row.get("care_recipient_id") == care_recipient_id
    ]
    logger.info(
        "Listed %d delivery(ies) for recipient %s", len(deliveries), care_recipient_id
    )
    return deliveries
