"""Tests for the Supervisor Agent: routing, escalation, approval, and audit trail."""

import pytest
from unittest.mock import patch, AsyncMock
from uuid import uuid4
from datetime import datetime, timezone

from src.models.schemas import CareEvent, ResolutionResult
from src.models.audit_log import get_audit_events, write_audit_event
from src.models.escalation_logic import classify_action
from src.agents.supervisor_agent import process_event, query_status, approve_pending_action


# ---------------------------------------------------------------------------
# Escalation logic tests
# ---------------------------------------------------------------------------


class TestClassifyAction:
    """Tests for deterministic classify_action()."""

    def test_auto_check_refill_status(self):
        """check_refill_status is autonomous."""
        assert classify_action("check_refill_status") == "auto"

    def test_auto_get_calendar(self):
        """get_calendar is autonomous."""
        assert classify_action("get_calendar") == "auto"

    def test_auto_synthesize_status(self):
        """synthesize_status is autonomous."""
        assert classify_action("synthesize_status") == "auto"

    def test_alert_order_refill(self):
        """order_refill requires alert."""
        assert classify_action("order_refill") == "alert"

    def test_alert_order_grocery(self):
        """order_grocery requires alert."""
        assert classify_action("order_grocery") == "alert"

    def test_alert_schedule_appointment(self):
        """schedule_appointment requires alert."""
        assert classify_action("schedule_appointment") == "alert"

    def test_approve_cancel_appointment(self):
        """cancel_appointment requires approval."""
        assert classify_action("cancel_appointment") == "approve"

    def test_approve_change_medication(self):
        """change_medication_schedule requires approval."""
        assert classify_action("change_medication_schedule") == "approve"

    def test_unknown_defaults_to_approve(self):
        """Unknown action defaults to 'approve' for safety."""
        assert classify_action("unknown_action_xyz") == "approve"


# ---------------------------------------------------------------------------
# process_event routing tests
# ---------------------------------------------------------------------------


class TestProcessEventRouting:
    """Tests for process_event() routing to specialized agents."""

    async def test_refill_low_routes_to_medication(self, temp_audit_db):
        """refill_low event is routed to the medication agent."""
        event = CareEvent(
            event_type="refill_low",
            care_recipient_id="cr-001",
            payload={"medication_id": "med-001"},
        )
        result: ResolutionResult = await process_event(event)

        assert result.resolved is True
        assert any("medication" in a.lower() for a in result.actions_taken)

    async def test_appointment_upcoming_routes_to_appointment(self, temp_audit_db):
        """appointment_upcoming event is routed to the appointment agent."""
        event = CareEvent(
            event_type="appointment_upcoming",
            care_recipient_id="cr-001",
            payload={},
        )
        result = await process_event(event)

        assert result.resolved is True
        assert any("appointment" in a.lower() for a in result.actions_taken)

    async def test_delivery_failed_routes_to_logistics(self, temp_audit_db):
        """delivery_failed event is routed to the logistics agent."""
        event = CareEvent(
            event_type="delivery_failed",
            care_recipient_id="cr-001",
            payload={"delivery_id": "del-003"},
        )
        result = await process_event(event)

        assert result.resolved is True
        assert any("logistics" in a.lower() for a in result.actions_taken)

    async def test_escalation_routes_to_communication(self, temp_audit_db):
        """When escalation is needed, the communication agent is invoked."""
        # del-003 is a failed pharmacy delivery (essential) → escalation
        event = CareEvent(
            event_type="delivery_failed",
            care_recipient_id="cr-001",
            payload={"delivery_id": "del-003"},
        )
        result = await process_event(event)

        assert result.escalation_required is True
        assert result.escalation_level in ("alert", "emergency")


# ---------------------------------------------------------------------------
# query_status tests
# ---------------------------------------------------------------------------


class TestQueryStatus:
    """Tests for query_status()."""

    async def test_returns_synthesized_status(self, temp_audit_db):
        """query_status returns a status string."""
        text = await query_status("cr-001", "What is the current status?")
        assert isinstance(text, str)
        assert "cr-001" in text


# ---------------------------------------------------------------------------
# approve_pending_action tests
# ---------------------------------------------------------------------------


class TestApprovePendingAction:
    """Tests for approve_pending_action()."""

    async def test_approve_executes_action(self, temp_audit_db):
        """Approving a pending action executes it via the correct agent."""
        # Create a pending audit event to approve
        action_id = write_audit_event(
            actor="medication",
            action_type="order_refill",
            care_recipient_id="cr-001",
            rationale="Refill needed",
            outcome="pending",
            correlation_id=str(uuid4()),
        )

        await approve_pending_action(action_id, approved=True)

        # Verify the action was resolved (no error raised)
        events = get_audit_events(care_recipient_id="cr-001")
        approve_events = [e for e in events if e["action_type"] == "approve_action"]
        assert len(approve_events) > 0

    async def test_reject_logs_rejection(self, temp_audit_db):
        """Rejecting a pending action logs a rejection audit event."""
        action_id = write_audit_event(
            actor="medication",
            action_type="cancel_appointment",
            care_recipient_id="cr-001",
            rationale="Cancel appointment",
            outcome="pending",
            correlation_id=str(uuid4()),
        )

        await approve_pending_action(action_id, approved=False)

        events = get_audit_events(care_recipient_id="cr-001")
        reject_events = [e for e in events if e["action_type"] == "reject_action"]
        assert len(reject_events) > 0
        assert any("rejected" in e["rationale"] for e in reject_events)

    async def test_double_resolve_raises(self, temp_audit_db):
        """Approving an already-resolved action raises ValueError."""
        action_id = write_audit_event(
            actor="medication",
            action_type="order_refill",
            care_recipient_id="cr-001",
            rationale="Refill needed",
            outcome="pending",
            correlation_id=str(uuid4()),
        )

        await approve_pending_action(action_id, approved=True)

        with pytest.raises(ValueError, match="already resolved"):
            await approve_pending_action(action_id, approved=True)

    async def test_nonexistent_action_raises(self, temp_audit_db):
        """Approving a non-existent action raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            await approve_pending_action("nonexistent-id", approved=True)


# ---------------------------------------------------------------------------
# Audit trail tests
# ---------------------------------------------------------------------------


class TestAuditTrail:
    """Tests for audit trail immutability and completeness."""

    async def test_process_event_writes_audit_events(self, temp_audit_db):
        """Every process_event call writes at least one audit event."""
        event = CareEvent(
            event_type="refill_low",
            care_recipient_id="cr-001",
            payload={"medication_id": "med-002"},
        )
        result = await process_event(event)

        # The supervisor writes at least a "pending" and a follow-up event
        assert len(result.audit_event_ids) >= 2

        # Verify events exist in the DB
        events = get_audit_events(care_recipient_id="cr-001")
        assert len(events) > 0

    def test_audit_immutability_update(self, temp_audit_db):
        """Attempt UPDATE on audit_events → expect exception."""
        import sqlite3
        from src.models.audit_log import init_audit_db as _init

        # Ensure triggers are created on the temp DB
        _init(temp_audit_db)

        event_id = write_audit_event(
            actor="medication",
            action_type="test",
            care_recipient_id="cr-001",
            rationale="test",
            outcome="pending",
            correlation_id=str(uuid4()),
            db_path=temp_audit_db,
        )

        conn = sqlite3.connect(temp_audit_db)
        try:
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE audit_events SET outcome='success' WHERE event_id=?",
                    (event_id,),
                )
        finally:
            conn.close()

    def test_audit_immutability_delete(self, temp_audit_db):
        """Attempt DELETE on audit_events → expect exception."""
        import sqlite3
        from src.models.audit_log import init_audit_db as _init

        _init(temp_audit_db)

        write_audit_event(
            actor="medication",
            action_type="test",
            care_recipient_id="cr-001",
            rationale="test",
            outcome="pending",
            correlation_id=str(uuid4()),
            db_path=temp_audit_db,
        )

        conn = sqlite3.connect(temp_audit_db)
        try:
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                cursor = conn.cursor()
                cursor.execute("DELETE FROM audit_events WHERE care_recipient_id='cr-001'")
        finally:
            conn.close()
