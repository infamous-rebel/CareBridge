"""Medication listing for a care recipient (read-only).

``GET /medications/{care_recipient_id}`` returns the recipient's medications from
the fixture data as domain :class:`~src.models.schemas.Medication` models. This
is a read-only view — it never orders refills or alters medication data
(AGENTS.md §1: the API coordinates, the Medication Agent acts).
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends

from src.api.dependencies import get_current_user
from src.api.schemas import Medication

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/medications", tags=["medications"])

FIXTURES_PATH = Path(__file__).resolve().parents[3] / "fixtures"


@router.get("/{care_recipient_id}", response_model=list[Medication])
async def list_medications(
    care_recipient_id: str, _user: dict = Depends(get_current_user)
) -> list[Medication]:
    """Return all medications for a care recipient.

    Args:
        care_recipient_id: The recipient whose medications to list.
        _user: Injected authenticated user.

    Returns:
        A list of ``Medication`` models (empty if none match).
    """
    with open(FIXTURES_PATH / "medications.json") as f:
        rows = json.load(f)
    meds = [
        Medication(**row)
        for row in rows
        if row.get("care_recipient_id") == care_recipient_id
    ]
    logger.info(
        "Listed %d medication(s) for recipient %s", len(meds), care_recipient_id
    )
    return meds
