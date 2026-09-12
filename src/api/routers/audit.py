"""Paginated, filterable read access to the immutable audit trail.

``GET /audit`` reads from ``src/models/audit_log.py`` (never modifying its
schema — AGENTS.md §3) and supports filtering by recipient, correlation id,
actor, action type, and outcome, plus page-based pagination.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.api import audit_query
from src.api.dependencies import get_current_user
from src.api.schemas import PaginatedAudit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=PaginatedAudit)
async def list_audit(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    care_recipient_id: Optional[str] = Query(default=None),
    correlation_id: Optional[str] = Query(default=None),
    actor: Optional[str] = Query(default=None),
    action_type: Optional[str] = Query(default=None),
    outcome: Optional[str] = Query(default=None),
    _user: dict = Depends(get_current_user),
) -> PaginatedAudit:
    """Return a page of audit events matching the supplied filters.

    Args:
        page: 1-based page number.
        page_size: Items per page (1..200).
        care_recipient_id: Filter by recipient.
        correlation_id: Filter by correlation id.
        actor: Filter by actor.
        action_type: Filter by action type.
        outcome: Filter by outcome.
        _user: Injected authenticated user.

    Returns:
        ``PaginatedAudit`` with the page of events and pagination metadata.
    """
    events = audit_query.fetch_events(
        care_recipient_id=care_recipient_id,
        correlation_id=correlation_id,
        actor=actor,
        action_type=action_type,
        outcome=outcome,
    )
    page_items, total, pages = audit_query.paginate(events, page, page_size)
    return PaginatedAudit(
        items=page_items, total=total, page=page, page_size=page_size, pages=pages
    )
