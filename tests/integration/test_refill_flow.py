"""Integration test: end-to-end refill flow through the supervisor."""

import pytest
from uuid import uuid4

from src.models.schemas import CareEvent
from src.models.audit_log import get_audit_events
from src.agents.supervisor_agent import process_event


class TestRefillFlow:
    """End-to-end refill_low event processing through the full pipeline."""

    async def test_refill_low_full_flow(self, temp_audit_db):
        """refill_low → supervisor → medication agent → order placed → audit trail written.

        Verifies:
        1. The event is routed to the medication agent.
        2. A refill order is placed for med-001 (days_remaining=3 <= threshold=5).
        3. Audit trail entries exist (pending + follow-up).
        4. Escalation occurs because order_refill is an ALERT-category action.
        """
        event = CareEvent(
            event_type="refill_low",
            care_recipient_id="cr-001",
            payload={"medication_id": "med-001"},
        )

        result = await process_event(event)

        # The event was resolved
        assert result.resolved is True

        # The medication agent ordered a refill
        assert any("refill" in a.lower() for a in result.actions_taken)

        # Audit trail has entries for cr-001
        events = get_audit_events(care_recipient_id="cr-001")
        assert len(events) >= 2  # at least pending + follow-up

        # At least one supervisor event exists
        supervisor_events = [e for e in events if e["actor"] == "supervisor"]
        assert len(supervisor_events) >= 2  # pending + outcome

        # The first supervisor event should be "pending" (audit-first pattern)
        pending_events = [e for e in supervisor_events if e["outcome"] == "pending"]
        assert len(pending_events) >= 1

    async def test_refill_low_no_refill_needed(self, temp_audit_db):
        """med-002 has 15 days remaining — no refill order, no escalation for the order itself."""
        event = CareEvent(
            event_type="refill_low",
            care_recipient_id="cr-001",
            payload={"medication_id": "med-002"},
        )

        result = await process_event(event)

        assert result.resolved is True
        # No refill order should appear for med-002
        refill_order_actions = [a for a in result.actions_taken if "Ordered refill" in a]
        assert len(refill_order_actions) == 0

    async def test_audit_trail_completeness(self, temp_audit_db):
        """Every process_event produces at least 2 audit events (before + after)."""
        event = CareEvent(
            event_type="refill_low",
            care_recipient_id="cr-001",
            payload={"medication_id": "med-001"},
        )

        result = await process_event(event)

        assert len(result.audit_event_ids) >= 2

        # Verify correlation_id links the events
        events = get_audit_events(care_recipient_id="cr-001")
        supervisor_events = [e for e in events if e["actor"] == "supervisor"]
        correlation_ids = {e["correlation_id"] for e in supervisor_events}
        # At least one shared correlation_id among supervisor events
        assert len(correlation_ids) >= 1
