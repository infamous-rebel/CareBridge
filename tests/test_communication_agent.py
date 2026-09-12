"""Tests for communication tools and the Communication Agent handler."""

import pytest
from unittest.mock import patch, AsyncMock
from uuid import uuid4
from datetime import datetime, timezone

from src.models.schemas import (
    AlertResult,
    CareEvent,
    FamilyPreferences,
    StatusSummary,
)
from src.tools.communication_tools import send_alert, synthesize_status, get_family_preferences
from src.agents.communication_agent import handle_communication_event


# ---------------------------------------------------------------------------
# Tool-level tests
# ---------------------------------------------------------------------------


class TestSendAlert:
    """Tests for send_alert()."""

    async def test_happy_path_alert_level(self, temp_audit_db):
        """send_alert with level='alert' returns AlertResult with sms,email channel."""
        result: AlertResult = await send_alert(
            recipient_id="cr-001",
            message="Test alert message",
            level="alert",
        )
        assert result.delivery_status == "sent"
        assert result.channel_used == "sms,email"
        assert result.sent_at is not None

    async def test_emergency_uses_all_channels(self, temp_audit_db):
        """send_alert with level='emergency' uses sms,email,phone."""
        result = await send_alert("cr-001", "Emergency!", "emergency")
        assert result.channel_used == "sms,email,phone"

    async def test_info_batches_to_digest(self, temp_audit_db):
        """send_alert with level='info' batches to daily digest."""
        result = await send_alert("cr-001", "FYI update", "info")
        assert result.channel_used == "digest"

    async def test_messaging_failure_raises(self, temp_audit_db):
        """When family member loading fails, send_alert raises RuntimeError."""
        with patch(
            "src.tools.communication_tools._load_family_members",
            side_effect=RuntimeError("Messaging API down"),
        ):
            with pytest.raises(RuntimeError, match="Messaging API failed"):
                await send_alert("cr-001", "Test", "alert")


class TestSynthesizeStatus:
    """Tests for synthesize_status()."""

    def test_returns_status_summary(self, temp_audit_db):
        """synthesize_status returns a StatusSummary."""
        result: StatusSummary = synthesize_status("cr-001")
        assert isinstance(result, StatusSummary)
        assert result.care_recipient_id == "cr-001"
        assert isinstance(result.summary_text, str)
        assert len(result.summary_text) > 0

    def test_empty_history(self, temp_audit_db):
        """For a recipient with no events, summary says 'No recent events'."""
        result = synthesize_status("cr-999")
        assert "No recent events" in result.summary_text


class TestGetFamilyPreferences:
    """Tests for get_family_preferences()."""

    def test_happy_path_three_members(self):
        """fam-001 has 3 family members with proper escalation order."""
        result: FamilyPreferences = get_family_preferences("fam-001")
        assert result.family_id == "fam-001"
        assert len(result.members) == 3
        assert len(result.escalation_order) == 3
        # Escalation order should be sorted by priority
        assert result.escalation_order[0] == "Emily Johnson"

    def test_invalid_family_raises(self):
        """Invalid family_id raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            get_family_preferences("fam-999")


# ---------------------------------------------------------------------------
# Agent-level tests
# ---------------------------------------------------------------------------


def _make_comm_event(
    level: str = "alert",
    message: str = "Test alert",
    care_recipient_id: str = "cr-001",
) -> CareEvent:
    """Helper to build a communication CareEvent."""
    return CareEvent(
        event_type="adherence_deviation",
        care_recipient_id=care_recipient_id,
        payload={"level": level, "message": message},
    )


class TestHandleCommunicationEvent:
    """Tests for handle_communication_event()."""

    async def test_alert_level(self, temp_audit_db):
        """Alert-level event sends alert and sets escalation_required=True."""
        event = _make_comm_event(level="alert")
        result = await handle_communication_event(event)

        assert result["escalation_required"] is True
        assert result["escalation_level"] == "alert"
        assert result["alert_result"] is not None
        assert result["alert_result"]["delivery_status"] == "sent"

    async def test_emergency_level(self, temp_audit_db):
        """Emergency-level event uses all channels."""
        event = _make_comm_event(level="emergency", message="Fall detected!")
        result = await handle_communication_event(event)

        assert result["escalation_required"] is True
        assert result["escalation_level"] == "emergency"
        assert result["alert_result"]["channel_used"] == "sms,email,phone"

    async def test_info_level_batches(self, temp_audit_db):
        """Info-level event is queued for daily digest."""
        event = _make_comm_event(level="info", message="Routine update")
        result = await handle_communication_event(event)

        assert result["escalation_required"] is False
        assert result["escalation_level"] == "info"
        assert result["alert_result"] is None
        assert any("digest" in a.lower() for a in result["actions_taken"])
