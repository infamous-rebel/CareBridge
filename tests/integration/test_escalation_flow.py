"""Integration test: end-to-end escalation flow when retries are exhausted."""

import pytest
from unittest.mock import patch, AsyncMock
from uuid import uuid4

from src.models.schemas import CareEvent
from src.models.audit_log import get_audit_events
from src.tools.retry import RetryExhausted
from src.agents.supervisor_agent import process_event


class TestEscalationFlow:
    """End-to-end: order_refill fails 3x → RetryExhausted → escalation to communication agent."""

    async def test_retry_exhausted_triggers_escalation(self, temp_audit_db):
        """When order_refill always fails, the full pipeline escalates to the family.

        Verifies:
        1. RetryExhausted is caught by the medication agent.
        2. The supervisor detects escalation_required.
        3. The communication agent is invoked (family alert sent).
        4. Audit trail contains an 'escalated' outcome entry.
        """
        event = CareEvent(
            event_type="refill_low",
            care_recipient_id="cr-001",
            payload={"medication_id": "med-001"},
        )

        async def failing_refill(*args, **kwargs):
            raise RuntimeError("Pharmacy API permanently unavailable")

        with patch(
            "src.agents.medication_agent.order_refill",
            side_effect=failing_refill,
        ):
            result = await process_event(event)

        # The event was resolved (not crashed)
        assert result.resolved is True

        # Escalation was triggered
        assert result.escalation_required is True
        assert result.escalation_level == "alert"

        # Communication agent was invoked (alert-related actions in the result)
        alert_actions = [a for a in result.actions_taken if "alert" in a.lower() or "Alert" in a]
        assert len(alert_actions) > 0

        # Audit trail has escalation evidence
        events = get_audit_events(care_recipient_id="cr-001")
        escalated_events = [e for e in events if e["outcome"] == "escalated"]
        assert len(escalated_events) >= 1

    async def test_essential_delivery_failure_escalates(self, temp_audit_db):
        """Failed pharmacy delivery (essential) triggers escalation through supervisor.

        del-003 is a pharmacy delivery that failed. The logistics agent
        should escalate immediately, and the supervisor should route to
        the communication agent.
        """
        event = CareEvent(
            event_type="delivery_failed",
            care_recipient_id="cr-001",
            payload={"delivery_id": "del-003"},
        )

        result = await process_event(event)

        assert result.resolved is True
        assert result.escalation_required is True
        assert result.escalation_level in ("alert", "emergency")

        # Verify communication agent was called (alert sent)
        comm_actions = [a for a in result.actions_taken if "alert" in a.lower() or "Alert" in a or "sent" in a.lower()]
        assert len(comm_actions) > 0

        # Audit trail has escalated entries
        events = get_audit_events(care_recipient_id="cr-001")
        assert any(e["outcome"] == "escalated" for e in events)

    async def test_adherence_deviation_escalates(self, temp_audit_db):
        """med-001 has moderate adherence deviation → escalation through supervisor."""
        event = CareEvent(
            event_type="adherence_deviation",
            care_recipient_id="cr-001",
            payload={"medication_id": "med-001"},
        )

        result = await process_event(event)

        assert result.resolved is True
        # med-001 has deviation_flag=True, severity=moderate → escalation_required
        assert result.escalation_required is True
        assert result.escalation_level == "alert"
