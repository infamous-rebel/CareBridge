"""Status endpoint — a synthesized care summary for one recipient.

``GET /status/{care_recipient_id}`` builds a :class:`StatusSummary` from the
current audit state via the deterministic ``synthesize_status`` tool (an AUTO
category action — no external API, no LLM). Read-only, so it returns 200 even
when the agent SDK is unavailable.
"""

import logging

from fastapi import APIRouter, Depends

from src.api.dependencies import get_current_user
from src.api.schemas import StatusSummary

logger = logging.getLogger(__name__)

router = APIRouter(tags=["status"])


@router.get("/status/{care_recipient_id}", response_model=StatusSummary)
async def get_status(
    care_recipient_id: str, _user: dict = Depends(get_current_user)
) -> StatusSummary:
    """Return a synthesized status summary for a care recipient.

    Args:
        care_recipient_id: The recipient to summarize.
        _user: Injected authenticated user (any role may read status).

    Returns:
        ``StatusSummary`` with summary text, recent events, and pending actions.
    """
    from src.tools.communication_tools import synthesize_status

    logger.info("Status summary requested for recipient %s", care_recipient_id)
    return synthesize_status(care_recipient_id)
