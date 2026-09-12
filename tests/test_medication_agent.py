"""Tests for medication tools and the Medication Agent handler."""

import pytest
from unittest.mock import patch, AsyncMock
from uuid import uuid4
from datetime import datetime, timezone

from src.models.schemas import CareEvent, RefillStatus, RefillOrder, AdherencePattern
from src.tools.medication_tools import check_refill_status, order_refill, detect_adherence_pattern
from src.tools.retry import RetryExhausted
from src.agents.medication_agent import handle_medication_event


# ---------------------------------------------------------------------------
# Tool-level tests
# ---------------------------------------------------------------------------


class TestCheckRefillStatus:
    """Tests for check_refill_status()."""

    def test_happy_path_med001(self):
        """med-001 (Lisinopril) has days_remaining=3, refill_eligible=True."""
        result: RefillStatus = check_refill_status("med-001")
        assert result.medication_id == "med-001"
        assert result.days_remaining == 3
        assert result.refill_eligible is True
        assert result.pharmacy_id == "pharm-001"

    def test_happy_path_med002_not_eligible(self):
        """med-002 (Metformin) has days_remaining=15, refill_eligible=False."""
        result = check_refill_status("med-002")
        assert result.days_remaining == 15
        assert result.refill_eligible is False

    def test_invalid_medication_raises(self):
        """Invalid medication_id raises ValueError."""
        with pytest.raises(ValueError, match="Medication not found"):
            check_refill_status("med-999")


class TestOrderRefill:
    """Tests for order_refill()."""

    async def test_happy_path_returns_placed(self, temp_audit_db):
        """Successful refill returns RefillOrder(status='placed')."""
        result: RefillOrder = await order_refill("med-001", "pharm-001")
        assert result.status == "placed"
        assert result.medication_id == "med-001"
        assert result.order_id  # non-empty UUID string

    async def test_api_failure_returns_failed(self, temp_audit_db):
        """Simulated API failure returns RefillOrder(status='failed').

        order_refill catches exceptions internally and returns a failed
        RefillOrder rather than raising. We mock uuid4 to succeed for the
        first calls (correlation_id, care_recipient lookup) and fail on
        the order_id call inside the try block.
        """
        from uuid import uuid4 as real_uuid4
        import src.tools.medication_tools as mod
        call_count = 0

        def failing_uuid():
            nonlocal call_count
            call_count += 1
            # First call: correlation_id — succeed
            if call_count <= 1:
                return real_uuid4()
            # Subsequent calls (order_id inside try block) — fail
            raise RuntimeError("API timeout")

        with patch("src.tools.medication_tools.uuid4", side_effect=failing_uuid):
            result = await order_refill("med-001", "pharm-001")
            assert result.status == "failed"
            assert result.failure_reason is not None


class TestDetectAdherencePattern:
    """Tests for detect_adherence_pattern()."""

    def test_med001_has_deviation(self):
        """med-001 returns deviation_flag=True, severity='moderate'."""
        result: AdherencePattern = detect_adherence_pattern("med-001")
        assert result.deviation_flag is True
        assert result.severity == "moderate"
        assert result.missed_doses == 2
        assert result.late_doses == 1

    def test_med002_good_adherence(self):
        """med-002 returns deviation_flag=False, severity='none'."""
        result = detect_adherence_pattern("med-002")
        assert result.deviation_flag is False
        assert result.severity == "none"

    def test_invalid_medication_raises(self):
        """Invalid medication_id raises ValueError."""
        with pytest.raises(ValueError, match="Medication not found"):
            detect_adherence_pattern("med-999")


# ---------------------------------------------------------------------------
# Agent-level tests
# ---------------------------------------------------------------------------


def _make_care_event(
    event_type: str = "refill_low",
    medication_id: str = "med-001",
    care_recipient_id: str = "cr-001",
) -> CareEvent:
    """Helper to build a CareEvent for medication testing."""
    return CareEvent(
        event_type=event_type,
        care_recipient_id=care_recipient_id,
        payload={"medication_id": medication_id},
    )


class TestHandleMedicationEvent:
    """Tests for handle_medication_event()."""

    async def test_refill_low_triggers_order(self, temp_audit_db):
        """refill_low event for med-001 should order a refill (days_remaining=3 <= 5)."""
        event = _make_care_event()
        result = await handle_medication_event(event)

        assert result["medication_id"] == "med-001"
        assert result["refill_order"] is not None
        assert result["refill_order"]["status"] == "placed"
        assert result["refill_status"]["days_remaining"] == 3

    async def test_med002_no_refill_needed(self, temp_audit_db):
        """med-002 has 15 days remaining — no refill should be ordered."""
        event = _make_care_event(medication_id="med-002")
        result = await handle_medication_event(event)

        assert result["refill_status"]["days_remaining"] == 15
        assert result["refill_order"] is None

    async def test_invalid_medication_returns_error(self, temp_audit_db):
        """Invalid medication_id returns error in actions_taken."""
        event = _make_care_event(medication_id="med-999")
        result = await handle_medication_event(event)

        assert any("error" in a for a in result["actions_taken"])
        assert result["escalation_required"] is False

    async def test_missing_medication_id_returns_error(self, temp_audit_db):
        """Event without medication_id returns error."""
        event = CareEvent(
            event_type="refill_low",
            care_recipient_id="cr-001",
            payload={},
        )
        result = await handle_medication_event(event)
        assert result["medication_id"] is None
        assert any("missing" in a for a in result["actions_taken"])

    async def test_retry_exhaustion_triggers_escalation(self, temp_audit_db):
        """When order_refill always raises, retry exhaustion triggers escalation."""
        event = _make_care_event()  # med-001 triggers refill

        # Make order_refill raise so with_retry exhausts all 3 attempts
        async def failing_refill(*args, **kwargs):
            raise RuntimeError("Pharmacy API timeout")

        with patch(
            "src.agents.medication_agent.order_refill",
            side_effect=failing_refill,
        ):
            result = await handle_medication_event(event)

        assert result["escalation_required"] is True
        assert result["escalation_level"] == "alert"
        assert any("escalation" in a.lower() for a in result["actions_taken"])
