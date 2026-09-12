"""Caregiver Q&A endpoint backed by the Supervisor Agent.

``POST /query`` routes a natural-language question to
``Supervisor.query_status(care_recipient_id, question)``. This is the
LLM-dependent route: if the Supervisor runtime is unavailable it degrades to
HTTP 503 with ``{"status": "degraded", "reason": ...}`` (SPEC section F).
"""

import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from src.api.dependencies import get_current_user, get_supervisor
from src.api.schemas import DegradedResponse, QueryRequest, QueryResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def query(
    body: QueryRequest, _user: dict = Depends(get_current_user)
) -> QueryResponse:
    """Answer a caregiver question about a recipient's care status.

    Args:
        body: The care recipient id and the natural-language question.
        _user: Injected authenticated user.

    Returns:
        ``QueryResponse`` with the synthesized answer, or a 503
        ``DegradedResponse`` when the Supervisor runtime is unavailable.
    """
    supervisor = get_supervisor()
    if supervisor is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=DegradedResponse(
                reason="Supervisor agent runtime unavailable"
            ).model_dump(),
        )

    logger.info(
        "Caregiver query for recipient %s by user %s",
        body.care_recipient_id,
        _user["user_id"],
    )
    answer = await supervisor.query_status(body.care_recipient_id, body.question)
    return QueryResponse(
        care_recipient_id=body.care_recipient_id,
        question=body.question,
        answer=answer,
        status="ok",
    )
