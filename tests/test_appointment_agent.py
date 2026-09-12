"""Tests for appointment tools and the Appointment Agent handler."""

import pytest
from unittest.mock import patch, AsyncMock
from uuid import uuid4
from datetime import datetime, timedelta, timezone

from src.models.schemas import CareEvent, Appointment, ChecklistResult
from src.tools.appointment_tools import get_calendar, schedule_appointment, send_prep_checklist
from src.agents.appointment_agent import handle_appointment_event


# ---------------------------------------------------------------------------
# Tool-level tests
# ---------------------------------------------------------------------------


class TestGetCalendar:
    """Tests for get_calendar()."""

    def test_happy_path_cr001(self):
        """get_calendar returns appointments for cr-001."""
        appointments = get_calendar("cr-001", horizon_days=365)
        assert len(appointments) > 0
        assert all(isinstance(a, Appointment) for a in appointments)
        assert all(a.care_recipient_id == "cr-001" for a in appointments)

    def test_invalid_recipient_raises(self):
        """Invalid care_recipient_id raises ValueError."""
        with pytest.raises(ValueError, match="No appointments found"):
            get_calendar("cr-999")


class TestScheduleAppointment:
    """Tests for schedule_appointment()."""

    async def test_happy_path(self, temp_audit_db):
        """schedule_appointment creates a new Appointment."""
        preferred = datetime.now(timezone.utc) + timedelta(days=3)
        result: Appointment = await schedule_appointment(
            provider_id="prov-001",
            care_recipient_id="cr-001",
            preferred_datetime=preferred,
        )
        assert result.care_recipient_id == "cr-001"
        assert result.appointment_id  # non-empty
        assert result.specialty == "General"

    async def test_simulated_failure(self, temp_audit_db):
        """When the calendar API mock raises, schedule_appointment raises RuntimeError."""
        with patch(
            "src.tools.appointment_tools._simulate_calendar_api",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Calendar API down"),
        ):
            with pytest.raises(RuntimeError, match="Calendar API call failed"):
                await schedule_appointment(
                    provider_id="prov-001",
                    care_recipient_id="cr-001",
                    preferred_datetime=datetime.now(timezone.utc) + timedelta(days=1),
                )


class TestSendPrepChecklist:
    """Tests for send_prep_checklist()."""

    def test_happy_path(self):
        """send_prep_checklist returns ChecklistResult(checklist_sent=True)."""
        result: ChecklistResult = send_prep_checklist("apt-001")
        assert result.checklist_sent is True
        assert result.appointment_id == "apt-001"
        assert result.delivery_status == "sent"
        assert result.sent_at is not None

    def test_invalid_appointment_raises(self):
        """Invalid appointment_id raises ValueError."""
        with pytest.raises(ValueError, match="Appointment not found"):
            send_prep_checklist("apt-999")


# ---------------------------------------------------------------------------
# Agent-level tests
# ---------------------------------------------------------------------------


def _make_appointment_event(
    care_recipient_id: str = "cr-001",
) -> CareEvent:
    """Helper to build an appointment_upcoming CareEvent."""
    return CareEvent(
        event_type="appointment_upcoming",
        care_recipient_id=care_recipient_id,
        payload={},
    )


class TestHandleAppointmentmentEvent:
    """Tests for handle_appointment_event()."""

    async def test_processes_upcoming_appointments(self, temp_audit_db):
        """handle_appointment_event retrieves calendar for cr-001."""
        event = _make_appointment_event()
        result = await handle_appointment_event(event)

        assert result["care_recipient_id"] == "cr-001"
        assert isinstance(result["actions_taken"], list)
        assert len(result["actions_taken"]) > 0

    async def test_no_appointments_for_unknown_recipient(self, temp_audit_db):
        """Unknown recipient returns 'no appointments' message."""
        event = _make_appointment_event(care_recipient_id="cr-999")
        result = await handle_appointment_event(event)

        assert result["care_recipient_id"] == "cr-999"
        assert any("No appointments" in a or "not found" in a.lower() for a in result["actions_taken"])

    async def test_result_structure(self, temp_audit_db):
        """Result dict has the expected keys."""
        event = _make_appointment_event()
        result = await handle_appointment_event(event)

        assert "care_recipient_id" in result
        assert "actions_taken" in result
        assert "logistics_coordination_needed" in result
        assert "checklists_sent" in result
        assert "transport_appointments" in result
