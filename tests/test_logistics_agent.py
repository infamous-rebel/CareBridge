"""Tests for logistics tools and the Logistics Agent handler."""

import pytest
from unittest.mock import patch, AsyncMock
from uuid import uuid4
from datetime import datetime, timezone

from src.models.schemas import CareEvent, DeliveryStatus, DeliveryOrder
from src.tools.logistics_tools import check_delivery_status, order_grocery, order_pharmacy_delivery
from src.agents.logistics_agent import handle_logistics_event


# ---------------------------------------------------------------------------
# Tool-level tests
# ---------------------------------------------------------------------------


class TestCheckDeliveryStatus:
    """Tests for check_delivery_status()."""

    def test_happy_path_del001_delivered(self):
        """del-001 has status='delivered'."""
        result: DeliveryStatus = check_delivery_status("del-001")
        assert result.delivery_id == "del-001"
        assert result.status == "delivered"
        assert result.failure_reason is None

    def test_del003_failed(self):
        """del-003 has status='failed' with a failure reason."""
        result = check_delivery_status("del-003")
        assert result.status == "failed"
        assert result.failure_reason == "Address not accessible"

    def test_invalid_delivery_raises(self):
        """Invalid delivery_id raises ValueError."""
        with pytest.raises(ValueError, match="Delivery not found"):
            check_delivery_status("del-999")


class TestOrderGrocery:
    """Tests for order_grocery()."""

    async def test_happy_path(self, temp_audit_db):
        """order_grocery succeeds and returns DeliveryOrder(status='placed')."""
        result: DeliveryOrder = await order_grocery(
            care_recipient_id="cr-001",
            items=["Milk", "Bread", "Eggs"],
            delivery_address="123 Care St",
        )
        assert result.status == "placed"
        assert result.order_id
        assert result.delivery_id
        assert result.expected_at is not None

    async def test_simulated_failure(self, temp_audit_db):
        """When the delivery API mock raises, order_grocery raises RuntimeError."""
        with patch(
            "src.tools.logistics_tools.write_audit_event",
            side_effect=[None, RuntimeError("API down")],
        ):
            # The second write_audit_event call (inside except block) would also fail,
            # so we need a different approach. Let's instead patch uuid4 to cause failure.
            pass

        # Simpler approach: patch the uuid4 call inside the try block to fail
        original_uuid = __import__("src.tools.logistics_tools", fromlist=["uuid4"]).uuid4
        call_count = 0

        def failing_uuid():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return original_uuid()
            raise RuntimeError("Delivery API timeout")

        with patch("src.tools.logistics_tools.uuid4", side_effect=failing_uuid):
            with pytest.raises(RuntimeError, match="Delivery API call failed"):
                await order_grocery("cr-001", ["Milk"], "123 Care St")


class TestOrderPharmacyDelivery:
    """Tests for order_pharmacy_delivery()."""

    async def test_happy_path(self, temp_audit_db):
        """order_pharmacy_delivery succeeds and returns DeliveryOrder(status='placed')."""
        result: DeliveryOrder = await order_pharmacy_delivery(
            medication_id="med-001",
            pharmacy_id="pharm-001",
            delivery_address="123 Care St",
        )
        assert result.status == "placed"
        assert result.order_id
        assert result.delivery_id


# ---------------------------------------------------------------------------
# Agent-level tests
# ---------------------------------------------------------------------------


def _make_delivery_event(
    delivery_id: str = "del-003",
    care_recipient_id: str = "cr-001",
) -> CareEvent:
    """Helper to build a delivery_failed CareEvent."""
    return CareEvent(
        event_type="delivery_failed",
        care_recipient_id=care_recipient_id,
        payload={"delivery_id": delivery_id},
    )


class TestHandleLogisticsEvent:
    """Tests for handle_logistics_event()."""

    async def test_delivery_failed_essential_escalation(self, temp_audit_db):
        """del-003 is a pharmacy (essential) delivery failure — should escalate."""
        event = _make_delivery_event(delivery_id="del-003")
        result = await handle_logistics_event(event)

        assert result["escalation_required"] is True
        assert result["escalation_level"] == "alert"
        assert any("escalated" in a for a in result["actions_taken"])

    async def test_delivery_delivered_no_escalation(self, temp_audit_db):
        """del-001 is already delivered — no escalation needed."""
        event = _make_delivery_event(delivery_id="del-001")
        result = await handle_logistics_event(event)

        assert result["escalation_required"] is False

    async def test_missing_delivery_id_escalates(self, temp_audit_db):
        """delivery_failed event without delivery_id triggers escalation."""
        event = CareEvent(
            event_type="delivery_failed",
            care_recipient_id="cr-001",
            payload={},
        )
        result = await handle_logistics_event(event)
        assert result["escalation_required"] is True
        assert result["escalation_level"] == "alert"

    async def test_invalid_delivery_id_escalates(self, temp_audit_db):
        """Unknown delivery_id triggers escalation."""
        event = _make_delivery_event(delivery_id="del-999")
        result = await handle_logistics_event(event)
        assert result["escalation_required"] is True
