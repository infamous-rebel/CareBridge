"""Logistics tools for CareBridge delivery management.

Provides delivery status checks and order placement for groceries
and pharmacy deliveries. External API calls are simulated with
fixture data (MCP servers are Day 2).
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from src.models.schemas import DeliveryStatus, DeliveryOrder
from src.models.audit_log import write_audit_event
from src.models.escalation_logic import classify_action

logger = logging.getLogger(__name__)

FIXTURES_PATH = Path(__file__).parent.parent.parent / "fixtures"


def check_delivery_status(delivery_id: str) -> DeliveryStatus:
    """Check the status of a delivery.

    Args:
        delivery_id: The delivery identifier.

    Returns:
        DeliveryStatus with current status and expected arrival.

    Raises:
        ValueError: If delivery_id not found.
    """
    delivery_file = FIXTURES_PATH / "delivery_history.json"
    with open(delivery_file) as f:
        history = json.load(f)

    for record in history:
        if record["delivery_id"] == delivery_id:
            expected_at = None
            if record.get("expected_at"):
                expected_at = datetime.fromisoformat(
                    record["expected_at"].replace("Z", "+00:00")
                )
            return DeliveryStatus(
                delivery_id=record["delivery_id"],
                status=record["status"],
                expected_at=expected_at,
                failure_reason=record.get("failure_reason"),
            )

    raise ValueError(f"Delivery not found: {delivery_id}")


async def order_grocery(
    care_recipient_id: str,
    items: list[str],
    delivery_address: str,
) -> DeliveryOrder:
    """Place a grocery delivery order.

    Args:
        care_recipient_id: The care recipient identifier.
        items: List of grocery items to order.
        delivery_address: Delivery address.

    Returns:
        DeliveryOrder with order details.

    Raises:
        RuntimeError: If the delivery API call fails.
    """
    action_type = "order_grocery"
    classification = classify_action(action_type)
    correlation_id = str(uuid4())

    # Audit BEFORE execution
    write_audit_event(
        actor="logistics",
        action_type=action_type,
        care_recipient_id=care_recipient_id,
        rationale=f"Placing grocery order ({len(items)} items) for delivery to {delivery_address}",
        outcome="pending",
        correlation_id=correlation_id,
    )

    try:
        # Simulate external delivery API call
        order_id = f"ord-{uuid4().hex[:8]}"
        delivery_id = f"del-{uuid4().hex[:8]}"
        expected_at = datetime.now(timezone.utc) + timedelta(hours=24)

        result = DeliveryOrder(
            order_id=order_id,
            delivery_id=delivery_id,
            status="placed",
            expected_at=expected_at,
        )

        # Audit success
        write_audit_event(
            actor="logistics",
            action_type=action_type,
            care_recipient_id=care_recipient_id,
            rationale=f"Grocery order {order_id} placed successfully, delivery {delivery_id} expected at {expected_at.isoformat()}",
            outcome="success",
            correlation_id=correlation_id,
        )

        logger.info(
            "Grocery order placed: order=%s delivery=%s classification=%s",
            order_id, delivery_id, classification,
        )
        return result

    except Exception as e:
        # Audit failure
        write_audit_event(
            actor="logistics",
            action_type=action_type,
            care_recipient_id=care_recipient_id,
            rationale=f"Grocery order failed: {e}",
            outcome="failure",
            correlation_id=correlation_id,
        )
        logger.error("Grocery order failed: %s", e)
        raise RuntimeError(f"Delivery API call failed: {e}") from e


async def order_pharmacy_delivery(
    medication_id: str,
    pharmacy_id: str,
    delivery_address: str,
) -> DeliveryOrder:
    """Place a pharmacy delivery order.

    Args:
        medication_id: The medication to deliver.
        pharmacy_id: The pharmacy to deliver from.
        delivery_address: Delivery address.

    Returns:
        DeliveryOrder with order details.

    Raises:
        RuntimeError: If the delivery API call fails.
    """
    # Derive care_recipient_id from medication fixtures (best-effort)
    care_recipient_id = "unknown"
    try:
        meds_file = FIXTURES_PATH / "medications.json"
        with open(meds_file) as f:
            medications = json.load(f)
        for med in medications:
            if med["medication_id"] == medication_id:
                care_recipient_id = med["care_recipient_id"]
                break
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        logger.warning(
            "Failed to resolve care_recipient_id for %s from fixtures",
            medication_id,
        )

    action_type = "order_pharmacy_delivery"
    classification = classify_action(action_type)
    correlation_id = str(uuid4())

    # Audit BEFORE execution
    write_audit_event(
        actor="logistics",
        action_type=action_type,
        care_recipient_id=care_recipient_id,
        rationale=f"Placing pharmacy delivery for medication {medication_id} from pharmacy {pharmacy_id} to {delivery_address}",
        outcome="pending",
        correlation_id=correlation_id,
    )

    try:
        # Simulate external delivery API call
        order_id = f"ord-{uuid4().hex[:8]}"
        delivery_id = f"del-{uuid4().hex[:8]}"
        expected_at = datetime.now(timezone.utc) + timedelta(hours=24)

        result = DeliveryOrder(
            order_id=order_id,
            delivery_id=delivery_id,
            status="placed",
            expected_at=expected_at,
        )

        # Audit success
        write_audit_event(
            actor="logistics",
            action_type=action_type,
            care_recipient_id=care_recipient_id,
            rationale=f"Pharmacy delivery {delivery_id} placed successfully for medication {medication_id}, expected at {expected_at.isoformat()}",
            outcome="success",
            correlation_id=correlation_id,
        )

        logger.info(
            "Pharmacy delivery placed: order=%s delivery=%s medication=%s classification=%s",
            order_id, delivery_id, medication_id, classification,
        )
        return result

    except Exception as e:
        # Audit failure
        write_audit_event(
            actor="logistics",
            action_type=action_type,
            care_recipient_id=care_recipient_id,
            rationale=f"Pharmacy delivery failed: {e}",
            outcome="failure",
            correlation_id=correlation_id,
        )
        logger.error("Pharmacy delivery failed: %s", e)
        raise RuntimeError(f"Delivery API call failed: {e}") from e
