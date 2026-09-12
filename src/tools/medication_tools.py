"""CareBridge medication tools — pharmacy integration.

Provides check_refill_status, order_refill, and detect_adherence_pattern.
External pharmacy APIs are simulated via fixture data (Day 2 MCP integration).
"""

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from uuid import uuid4

from src.models.schemas import RefillStatus, RefillOrder, AdherencePattern
from src.models.audit_log import write_audit_event
from src.models.escalation_logic import classify_action
from src.tools.retry import with_retry, RetryExhausted

logger = logging.getLogger(__name__)

FIXTURES_PATH = Path(__file__).parent.parent.parent / "fixtures"


def _load_medications() -> list[dict]:
    """Load medication fixtures from the JSON file.

    Returns:
        List of medication dictionaries from fixtures/medications.json.
    """
    with open(FIXTURES_PATH / "medications.json") as f:
        return json.load(f)


def check_refill_status(medication_id: str) -> RefillStatus:
    """Check the refill status of a medication.

    Loads medication data from fixtures and computes refill eligibility
    based on days_remaining vs. refill_threshold.

    Args:
        medication_id: The medication identifier.

    Returns:
        RefillStatus with days_remaining, refill_eligible, pharmacy_id.

    Raises:
        ValueError: If medication_id not found in fixtures.
    """
    medications = _load_medications()

    for med in medications:
        if med["medication_id"] == medication_id:
            days_remaining: int = med["days_remaining"]
            refill_threshold: int = med.get("refill_threshold", 5)
            return RefillStatus(
                medication_id=medication_id,
                days_remaining=days_remaining,
                refill_eligible=days_remaining <= refill_threshold,
                pharmacy_id=med["pharmacy_id"],
            )

    raise ValueError(f"Medication not found: {medication_id}")


async def order_refill(medication_id: str, pharmacy_id: str) -> RefillOrder:
    """Order a medication refill from the pharmacy.

    Writes a 'pending' audit event BEFORE executing the pharmacy API call,
    then writes a follow-up event with the final outcome.

    Args:
        medication_id: The medication to refill.
        pharmacy_id: The pharmacy to order from.

    Returns:
        RefillOrder with order_id and status ("placed" or "failed").

    Raises:
        RuntimeError: If the pharmacy API call fails after audit logging.
    """
    correlation_id = str(uuid4())

    # Write "before action" audit event with outcome="pending"
    write_audit_event(
        actor="medication",
        action_type="order_refill",
        care_recipient_id="unknown",  # resolved below if possible
        rationale=f"Ordering refill for {medication_id} from pharmacy {pharmacy_id}",
        outcome="pending",
        correlation_id=correlation_id,
    )

    # Attempt to resolve care_recipient_id from fixtures for audit accuracy
    care_recipient_id = "unknown"
    try:
        medications = _load_medications()
        for med in medications:
            if med["medication_id"] == medication_id:
                care_recipient_id = med["care_recipient_id"]
                break
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        logger.warning(
            "Failed to resolve care_recipient_id for %s from fixtures: %s",
            medication_id, e,
        )

    try:
        # Simulate pharmacy API call (mock — real MCP integration on Day 2)
        order_id = str(uuid4())
        estimated_delivery = date.today() + timedelta(days=3)

        logger.info(
            f"Refill order placed: order_id={order_id}, "
            f"medication={medication_id}, pharmacy={pharmacy_id}"
        )

        # Write success follow-up audit event
        write_audit_event(
            actor="medication",
            action_type="order_refill",
            care_recipient_id=care_recipient_id,
            rationale=f"Refill for {medication_id} successfully placed with pharmacy {pharmacy_id}",
            outcome="success",
            correlation_id=correlation_id,
        )

        return RefillOrder(
            order_id=order_id,
            medication_id=medication_id,
            status="placed",
            estimated_delivery=estimated_delivery,
        )

    except Exception as e:
        logger.error(f"Pharmacy API call failed for {medication_id}: {e}")

        # Write failure follow-up audit event
        write_audit_event(
            actor="medication",
            action_type="order_refill",
            care_recipient_id=care_recipient_id,
            rationale=f"Refill for {medication_id} failed: {e}",
            outcome="failure",
            correlation_id=correlation_id,
        )

        return RefillOrder(
            order_id="",
            medication_id=medication_id,
            status="failed",
            failure_reason=str(e),
        )


def detect_adherence_pattern(
    medication_id: str, window_days: int = 7
) -> AdherencePattern:
    """Detect medication adherence patterns over a time window.

    Mock implementation returning simulated adherence data. For med-001
    (Lisinopril, low refill) returns moderate deviation; for all others
    returns good adherence.

    Args:
        medication_id: The medication to analyze.
        window_days: Number of days to analyze (default 7).

    Returns:
        AdherencePattern with deviation analysis.

    Raises:
        ValueError: If medication_id not found in fixtures.
    """
    medications = _load_medications()

    found = False
    for med in medications:
        if med["medication_id"] == medication_id:
            found = True
            break

    if not found:
        raise ValueError(f"Medication not found: {medication_id}")

    # med-001 (Lisinopril) has low days_remaining → simulate adherence issues
    if medication_id == "med-001":
        logger.info(
            f"Adherence deviation detected for {medication_id}: "
            f"missed_doses=2, late_doses=1, severity=moderate"
        )
        return AdherencePattern(
            medication_id=medication_id,
            missed_doses=2,
            late_doses=1,
            deviation_flag=True,
            severity="moderate",
        )

    # All other medications: good adherence
    logger.info(f"Good adherence for {medication_id} over {window_days} days")
    return AdherencePattern(
        medication_id=medication_id,
        missed_doses=0,
        late_doses=0,
        deviation_flag=False,
        severity="none",
    )
