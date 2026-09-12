"""CareBridge Pharmacy MCP server — in-process mock of the pharmacy API.

Runs in-process via the Qoder Agent SDK's ``create_sdk_mcp_server`` / ``@tool``
helpers (architecture.md §5, ADR-002: in-process MCP for custom tools). Backs
the Medication Agent with three tools (SPEC.md §6.1):

* ``check_refill_status(medication_id)`` — read-only refill status
* ``order_refill(medication_id, pharmacy_id)`` — places a refill, with a 10%
  simulated timeout so ``with_retry`` in the caller is exercised
* ``get_medication_schedule(care_recipient_id)`` — medications for a recipient

Data source: ``fixtures/medications.json``. Every tool call writes exactly one
audit event (actor="medication") whose outcome reflects success or failure.

Each MCP tool is exposed two ways:

1. A typed business function carrying the contract signature from SPEC.md
   (e.g. ``check_refill_status(medication_id: str) -> dict``) that performs the
   work and the audit logging. These are directly callable and unit-testable.
2. A thin ``@tool``-decorated async adapter that unpacks the MCP ``args`` dict,
   calls the business function, and wraps the result in the MCP content-block
   envelope. The Qoder SDK requires tool handlers to be
   ``async def handler(args: dict) -> dict`` with a separate ``input_schema``;
   the typed business functions keep the spec'd signatures intact.
"""

import json
import logging
import random
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

from qoder_agent_sdk import create_sdk_mcp_server, tool

from src.models.audit_log import write_audit_event
from src.models.schemas import Medication, RefillOrder, RefillStatus
from src.tools.retry import with_retry

logger = logging.getLogger(__name__)

FIXTURES_PATH = Path(__file__).parent.parent.parent / "fixtures"

# Audit actor for every tool on this server (AGENTS.md §7).
_ACTOR = "medication"

# Simulated pharmacy timeout rate for order_refill (SPEC.md §6.1: 10%).
PHARMACY_FAILURE_RATE = 0.10


class PharmacyTimeoutError(Exception):
    """Raised when the simulated pharmacy API times out on a refill order."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_medications() -> list[dict]:
    """Load medication fixtures from ``fixtures/medications.json``.

    Returns:
        List of raw medication dictionaries.

    Raises:
        FileNotFoundError: If the fixtures file is missing.
        json.JSONDecodeError: If the fixtures file contains invalid JSON.
    """
    with open(FIXTURES_PATH / "medications.json") as f:
        return json.load(f)


def _resolve_recipient(medication_id: str) -> str:
    """Resolve the care_recipient_id that owns a medication (best-effort).

    The audit trail requires a care_recipient_id, but pharmacy tools key off
    medication_id. Per AGENTS.md the value is resolved internally from fixtures
    rather than added to the tool signature.

    Args:
        medication_id: The medication identifier.

    Returns:
        The owning care_recipient_id, or "unknown" if it cannot be resolved.
    """
    try:
        for med in _load_medications():
            if med.get("medication_id") == medication_id:
                return med.get("care_recipient_id", "unknown")
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        logger.warning(
            "Could not resolve care_recipient_id for %s: %s", medication_id, e
        )
    return "unknown"


def _audit(
    action_type: str,
    care_recipient_id: str,
    rationale: str,
    outcome: str,
    correlation_id: str,
) -> None:
    """Write one pharmacy audit event (actor="medication").

    Args:
        action_type: The MCP tool name.
        care_recipient_id: FK to the care recipient.
        rationale: One-sentence plain-language reason for the action.
        outcome: "success" or "failure".
        correlation_id: UUID shared across events for the same logical action.
    """
    write_audit_event(
        actor=_ACTOR,
        action_type=action_type,
        care_recipient_id=care_recipient_id,
        rationale=rationale,
        outcome=outcome,
        correlation_id=correlation_id,
    )


def _mcp_result(payload: object) -> dict:
    """Wrap a tool payload in the MCP content-block envelope.

    Args:
        payload: JSON-serialisable tool result (dict or list of dicts).

    Returns:
        ``{"content": [{"type": "text", "text": <json>}]}``.
    """
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


# ---------------------------------------------------------------------------
# Tool business logic (spec signatures)
# ---------------------------------------------------------------------------

def check_refill_status(medication_id: str) -> dict:
    """Check the refill status of a medication.

    Args:
        medication_id: The medication identifier.

    Returns:
        RefillStatus as a dict with keys: medication_id, days_remaining
        (realistic value from the fixture), refill_eligible
        (days_remaining <= refill_threshold), pharmacy_id.

    Raises:
        ValueError: If medication_id is not present in the fixtures.
    """
    correlation_id = str(uuid4())
    care_recipient_id = _resolve_recipient(medication_id)
    try:
        medications = _load_medications()
        match = next(
            (m for m in medications if m["medication_id"] == medication_id), None
        )
        if match is None:
            raise ValueError(f"Medication not found: {medication_id}")

        days_remaining = int(match["days_remaining"])
        refill_threshold = int(match.get("refill_threshold", 5))
        status = RefillStatus(
            medication_id=medication_id,
            days_remaining=days_remaining,
            refill_eligible=days_remaining <= refill_threshold,
            pharmacy_id=match["pharmacy_id"],
        )

        _audit(
            "check_refill_status",
            care_recipient_id,
            f"Checked refill status for {medication_id}: "
            f"{days_remaining} day(s) remaining",
            "success",
            correlation_id,
        )
        logger.info(
            "check_refill_status: %s -> %d day(s), eligible=%s",
            medication_id, days_remaining, status.refill_eligible,
        )
        return status.model_dump(mode="json")
    except Exception as e:
        _audit(
            "check_refill_status",
            care_recipient_id,
            f"Refill status check failed for {medication_id}: {e}",
            "failure",
            correlation_id,
        )
        logger.error("check_refill_status failed for %s: %s", medication_id, e)
        raise


async def _simulate_pharmacy_order(medication_id: str, pharmacy_id: str) -> dict:
    """Simulate the external pharmacy order API call (the retriable unit).

    Fails with probability ``PHARMACY_FAILURE_RATE`` so that ``with_retry`` in
    ``order_refill`` is genuinely exercised.

    Args:
        medication_id: The medication to refill.
        pharmacy_id: The pharmacy fulfilling the refill.

    Returns:
        Dict with ``order_id`` (UUID) and ``estimated_delivery`` (date, +1 day).

    Raises:
        PharmacyTimeoutError: On a simulated timeout (~10% of calls).
    """
    if random.random() < PHARMACY_FAILURE_RATE:
        raise PharmacyTimeoutError(
            f"Pharmacy API timed out ordering refill for {medication_id} "
            f"from {pharmacy_id}"
        )
    return {
        "order_id": str(uuid4()),
        "estimated_delivery": date.today() + timedelta(days=1),
    }


async def order_refill(medication_id: str, pharmacy_id: str) -> dict:
    """Order a medication refill from the pharmacy.

    The simulated pharmacy call times out ~10% of the time; ``with_retry``
    retries up to 3× with exponential backoff (1s, 2s, 4s). If every attempt
    fails, ``RetryExhausted`` propagates after a failure audit event is written.

    Args:
        medication_id: The medication to refill.
        pharmacy_id: The pharmacy to order from.

    Returns:
        RefillOrder as a dict with keys: order_id, medication_id,
        status ("placed"), estimated_delivery (ISO date), failure_reason (None).

    Raises:
        RetryExhausted: If the pharmacy call fails on all retry attempts.
    """
    correlation_id = str(uuid4())
    care_recipient_id = _resolve_recipient(medication_id)
    try:
        raw = await with_retry(_simulate_pharmacy_order, medication_id, pharmacy_id)
        order = RefillOrder(
            order_id=raw["order_id"],
            medication_id=medication_id,
            status="placed",
            estimated_delivery=raw["estimated_delivery"],
        )

        _audit(
            "order_refill",
            care_recipient_id,
            f"Ordered refill {order.order_id} for {medication_id} "
            f"from pharmacy {pharmacy_id}",
            "success",
            correlation_id,
        )
        logger.info(
            "order_refill: placed %s for %s via %s",
            order.order_id, medication_id, pharmacy_id,
        )
        return order.model_dump(mode="json")
    except Exception as e:
        _audit(
            "order_refill",
            care_recipient_id,
            f"Refill order for {medication_id} from {pharmacy_id} failed: {e}",
            "failure",
            correlation_id,
        )
        logger.error(
            "order_refill failed for %s via %s: %s",
            medication_id, pharmacy_id, e,
        )
        raise


def get_medication_schedule(care_recipient_id: str) -> list[dict]:
    """Get the medication schedule for a care recipient.

    Args:
        care_recipient_id: The care recipient identifier.

    Returns:
        List of Medication dicts (medication_id, name, dosage, frequency,
        refill_threshold, pharmacy_id, care_recipient_id) for the recipient.
        Empty list if the recipient has no medications on file.

    Raises:
        FileNotFoundError: If the fixtures file is missing.
        json.JSONDecodeError: If the fixtures file contains invalid JSON.
    """
    correlation_id = str(uuid4())
    try:
        medications = _load_medications()
        schedule = [
            Medication(**med).model_dump(mode="json")
            for med in medications
            if med.get("care_recipient_id") == care_recipient_id
        ]

        _audit(
            "get_medication_schedule",
            care_recipient_id,
            f"Retrieved medication schedule for {care_recipient_id}: "
            f"{len(schedule)} medication(s)",
            "success",
            correlation_id,
        )
        logger.info(
            "get_medication_schedule: %d medication(s) for %s",
            len(schedule), care_recipient_id,
        )
        return schedule
    except Exception as e:
        _audit(
            "get_medication_schedule",
            care_recipient_id,
            f"Medication schedule retrieval failed for {care_recipient_id}: {e}",
            "failure",
            correlation_id,
        )
        logger.error(
            "get_medication_schedule failed for %s: %s", care_recipient_id, e
        )
        raise


# ---------------------------------------------------------------------------
# MCP tool adapters + server
# ---------------------------------------------------------------------------

@tool(
    "check_refill_status",
    "Check refill status and days remaining for a medication.",
    {"medication_id": str},
)
async def _check_refill_status_tool(args: dict) -> dict:
    """MCP adapter for :func:`check_refill_status`.

    Args:
        args: MCP arguments dict; requires ``medication_id``.

    Returns:
        MCP content-block envelope wrapping the RefillStatus dict.
    """
    return _mcp_result(check_refill_status(args["medication_id"]))


@tool(
    "order_refill",
    "Order a medication refill from a pharmacy.",
    {"medication_id": str, "pharmacy_id": str},
)
async def _order_refill_tool(args: dict) -> dict:
    """MCP adapter for :func:`order_refill`.

    Args:
        args: MCP arguments dict; requires ``medication_id`` and ``pharmacy_id``.

    Returns:
        MCP content-block envelope wrapping the RefillOrder dict.
    """
    return _mcp_result(
        await order_refill(args["medication_id"], args["pharmacy_id"])
    )


@tool(
    "get_medication_schedule",
    "List the medications scheduled for a care recipient.",
    {"care_recipient_id": str},
)
async def _get_medication_schedule_tool(args: dict) -> dict:
    """MCP adapter for :func:`get_medication_schedule`.

    Args:
        args: MCP arguments dict; requires ``care_recipient_id``.

    Returns:
        MCP content-block envelope wrapping the list of Medication dicts.
    """
    return _mcp_result(get_medication_schedule(args["care_recipient_id"]))


pharmacy_server = create_sdk_mcp_server(
    name="pharmacy",
    version="1.0.0",
    tools=[
        _check_refill_status_tool,
        _order_refill_tool,
        _get_medication_schedule_tool,
    ],
)
