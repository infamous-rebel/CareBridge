"""Integration test: end-to-end approval flow through the supervisor."""

import pytest
from unittest.mock import patch
from uuid import uuid4

from src.models.schemas import CareEvent
from src.models.audit_log import get_audit_events, write_audit_event
from src.agents.supervisor_agent import process_event, approve_pending_action


class TestApprovalFlow:
    """End-to-end: create pending action → approve → execute → verify audit trail."""

    async def test_approve_and_execute(self, temp_audit_db):
        """Approving a pending order_refill action executes it and writes authorization_ref.

        Verifies:
        1. A pending action is created in the audit trail.
        2. approve_pending_action(approved=True) executes the action.
        3. Audit trail contains approval and execution events with authorization_ref.
        """
        # Step 1: Create a pending action
        correlation_id = str(uuid4())
        action_id = write_audit_event(
            actor="medication",
            action_type="order_refill",
            care_recipient_id="cr-001",
            rationale="Refill needed for med-001",
            outcome="pending",
            correlation_id=correlation_id,
        )

        # Step 2: Approve the action
        await approve_pending_action(action_id, approved=True)

        # Step 3: Verify audit trail
        events = get_audit_events(care_recipient_id="cr-001")

        # Should have an approve_action event with authorization_ref
        approve_events = [
            e for e in events
            if e["action_type"] == "approve_action" and e["actor"] == "human"
        ]
        assert len(approve_events) >= 1

        # At least one event should reference the original action_id
        auth_refs = [e.get("authorization_ref") for e in events]
        assert action_id in auth_refs

        # Should have execution result (success or failure from supervisor)
        exec_events = [
            e for e in events
            if e["action_type"] == "approve_action" and e["actor"] == "supervisor"
        ]
        assert len(exec_events) >= 1

    async def test_reject_action(self, temp_audit_db):
        """Rejecting a pending action logs rejection without execution.

        Verifies:
        1. A pending action is created.
        2. approve_pending_action(approved=False) logs rejection.
        3. No execution events exist.
        """
        action_id = write_audit_event(
            actor="appointment",
            action_type="cancel_appointment",
            care_recipient_id="cr-001",
            rationale="Cancel cardiology appointment",
            outcome="pending",
            correlation_id=str(uuid4()),
        )

        await approve_pending_action(action_id, approved=False)

        events = get_audit_events(care_recipient_id="cr-001")

        # Should have a reject_action event
        reject_events = [
            e for e in events
            if e["action_type"] == "reject_action"
        ]
        assert len(reject_events) >= 1
        assert any("rejected" in e["rationale"].lower() for e in reject_events)

        # authorization_ref should point to the original action
        assert any(e.get("authorization_ref") == action_id for e in reject_events)

        # No supervisor execution event for a rejected action
        supervisor_exec = [
            e for e in events
            if e["actor"] == "supervisor" and e["action_type"] in ("approve_action", "reject_action")
        ]
        assert len(supervisor_exec) == 0

    async def test_full_event_then_approval_flow(self, temp_audit_db):
        """Process a refill_low event, then separately approve a pending action.

        This tests that the audit trail correctly records both flows independently.
        """
        # Process a refill event (will auto-execute for med-001)
        event = CareEvent(
            event_type="refill_low",
            care_recipient_id="cr-001",
            payload={"medication_id": "med-001"},
        )
        result = await process_event(event)
        assert result.resolved is True

        # Create and approve a separate pending action
        action_id = write_audit_event(
            actor="medication",
            action_type="change_medication_schedule",
            care_recipient_id="cr-001",
            rationale="Adjust Lisinopril timing",
            outcome="pending",
            correlation_id=str(uuid4()),
        )

        await approve_pending_action(action_id, approved=True)

        # Verify both flows left audit entries
        events = get_audit_events(care_recipient_id="cr-001")
        assert len(events) >= 4  # refill flow (2+) + approval flow (2+)

        # The approval flow should reference the action
        approval_events = [e for e in events if e.get("authorization_ref") == action_id]
        assert len(approval_events) >= 1
