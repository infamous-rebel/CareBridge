"""CareBridge Delivery MCP server — in-process mock of the delivery API.

Runs in-process via the Qoder Agent SDK's ``create_sdk_mcp_server`` / ``@tool``
helpers (architecture.md §5, ADR-002). Backs the Logistics Agent with three
tools (SPEC.md §6.3):

* ``check_delivery_status(delivery_id)`` — read status from delivery history
* ``order_grocery(care_recipient_id, items, delivery_address)`` — place a
  grocery order (15% simulated failure)
* ``order_pharmacy_delivery(medication_id, pharmacy_id, delivery_address)`` —
  place a pharmacy delivery (15% simulated failure)

Data source: ``fixtures/delivery_history.json`` for status checks and
``fixtures/medications.json`` to resolve the recipient for pharmacy deliveries.
Order tools fail ~15% of the time (``DeliveryFailedError``) so ``with_retry`` in
the caller is exercised. Every tool call writes exactly one audit event
(actor="logistics").

Per AGENTS.md §10 the delivery address is PII: it is used to place the order but
is never written to the audit trail or logs — those reference IDs only.

As in the other servers, each tool is a typed business function (the SPEC
contract) plus a thin ``@tool`` async adapter bridging the Qoder SDK's
``async def handler(args: dict) -> dict`` convention.
"""

import json
import logging
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from qoder_agent_sdk import create_sdk_mcp_server, tool

from src.models.audit_log import write_audit_event
from src.models.schemas import DeliveryStatus
from src.tools.retry import with_retry

logger = logging.getLogger(__name__)

FIXTURES_PATH = Path(__file__).parent.parent.parent / "fixtures"

# Audit actor for every tool on this server (AGENTS.md §7).
_ACTOR = "logistics"

# Simulated delivery failure rate for order tools (SPEC.md §6.3: 15%).
DELIVERY_FAILURE_RATE = 0.15


class DeliveryFailedError(Exception):
    """Raised when the simulated delivery API fails to place an order."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_delivery_history() -> list[dict]:
    """Load delivery history fixtures from ``fixtures/delivery_history.json``.

    Returns:
        List of raw delivery record dictionaries.

    Raises:
        FileNotFoundError: If the fixtures file is missing.
        json.JSONDecodeError: If the fixtures file contains invalid JSON.
    """
    with open(FIXTURES_PATH / "delivery_history.json") as f:
        return json.load(f)


def _resolve_recipient_for_medication(medication_id: str) -> str:
    """Resolve the care_recipient_id that owns a medication (best-effort).

    Args:
        medication_id: The medication identifier.

    Returns:
        The owning care_recipient_id, or "unknown" if it cannot be resolved.
    """
    try:
        with open(FIXTURES_PATH / "medications.json") as f:
            medications = json.load(f)
        for med in medications:
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
    """Write one delivery audit event (actor="logistics").

    Args:
        action_type: The MCP tool name.
        care_recipient_id: FK to the care recipient.
        rationale: One-sentence plain-language reason (IDs only — no PII).
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


async def _simulate_delivery_order(description: str) -> dict:
    """Simulate the external delivery order API call (the retriable unit).

    Fails with probability ``DELIVERY_FAILURE_RATE`` so that ``with_retry`` in
    the order tools is genuinely exercised.

    Args:
        description: Human-readable order description for the failure message
            (IDs only — never the delivery address).

    Returns:
        Dict with ``order_id`` (UUID) and ``estimated_delivery``
        (ISO datetime, now + 1 day).

    Raises:
        DeliveryFailedError: On a simulated failure (~15% of calls).
    """
    if random.random() < DELIVERY_FAILURE_RATE:
        raise DeliveryFailedError(f"Delivery API failed while placing {description}")
    return {
        "order_id": str(uuid4()),
        "estimated_delivery": (
            datetime.now(timezone.utc) + timedelta(days=1)
        ).isoformat(),
    }


# ---------------------------------------------------------------------------
# Tool business logic (spec signatures)
# ---------------------------------------------------------------------------

def check_delivery_status(delivery_id: str) -> dict:
    """Check the status of a delivery.

    Args:
        delivery_id: The delivery identifier.

    Returns:
        DeliveryStatus as a dict with keys: delivery_id, status
        ("pending" | "in_transit" | "delivered" | "failed"), expected_at
        (ISO datetime or None), failure_reason (or None).

    Raises:
        ValueError: If delivery_id is not present in the fixtures.
    """
    correlation_id = str(uuid4())
    care_recipient_id = "unknown"
    try:
        history = _load_delivery_history()
        match = next(
            (r for r in history if r["delivery_id"] == delivery_id), None
        )
        if match is None:
            raise ValueError(f"Delivery not found: {delivery_id}")

        care_recipient_id = match.get("care_recipient_id", "unknown")
        expected_at = None
        if match.get("expected_at"):
            expected_at = datetime.fromisoformat(
                match["expected_at"].replace("Z", "+00:00")
            )
        status = DeliveryStatus(
            delivery_id=match["delivery_id"],
            status=match["status"],
            expected_at=expected_at,
            failure_reason=match.get("failure_reason"),
        )

        _audit(
            "check_delivery_status",
            care_recipient_id,
            f"Checked delivery status for {delivery_id}: {status.status}",
            "success",
            correlation_id,
        )
        logger.info(
            "check_delivery_status: %s -> %s", delivery_id, status.status
        )
        return status.model_dump(mode="json")
    except Exception as e:
        _audit(
            "check_delivery_status",
            care_recipient_id,
            f"Delivery status check failed for {delivery_id}: {e}",
            "failure",
            correlation_id,
        )
        logger.error("check_delivery_status failed for %s: %s", delivery_id, e)
        raise


async def order_grocery(
    care_recipient_id: str,
    items: list[str],
    delivery_address: str,
) -> dict:
    """Place a grocery delivery order.

    The simulated delivery call fails ~15% of the time; ``with_retry`` retries
    up to 3× with exponential backoff. If every attempt fails,
    ``RetryExhausted`` propagates after a failure audit event is written.

    Args:
        care_recipient_id: The care recipient identifier.
        items: List of grocery items to order.
        delivery_address: Delivery address (PII — used, never logged).

    Returns:
        Dict ``{"order_id": <UUID>, "status": "placed",
        "estimated_delivery": <ISO datetime, now + 1 day>}``.

    Raises:
        RetryExhausted: If the delivery call fails on all retry attempts.
    """
    correlation_id = str(uuid4())
    try:
        raw = await with_retry(
            _simulate_delivery_order, f"grocery order for {care_recipient_id}"
        )
        result = {
            "order_id": raw["order_id"],
            "status": "placed",
            "estimated_delivery": raw["estimated_delivery"],
        }

        _audit(
            "order_grocery",
            care_recipient_id,
            f"Placed grocery order ({len(items)} item(s)) for {care_recipient_id}",
            "success",
            correlation_id,
        )
        logger.info(
            "order_grocery: placed %s (%d item(s)) for %s",
            result["order_id"], len(items), care_recipient_id,
        )
        return result
    except Exception as e:
        _audit(
            "order_grocery",
            care_recipient_id,
            f"Grocery order for {care_recipient_id} failed: {e}",
            "failure",
            correlation_id,
        )
        logger.error("order_grocery failed for %s: %s", care_recipient_id, e)
        raise


async def order_pharmacy_delivery(
    medication_id: str,
    pharmacy_id: str,
    delivery_address: str,
) -> dict:
    """Place a pharmacy delivery order.

    The simulated delivery call fails ~15% of the time; ``with_retry`` retries
    up to 3× with exponential backoff. The care_recipient_id is resolved from
    the medication fixtures (it is not part of the spec'd signature).

    Args:
        medication_id: The medication to deliver.
        pharmacy_id: The pharmacy to deliver from.
        delivery_address: Delivery address (PII — used, never logged).

    Returns:
        Dict ``{"order_id": <UUID>, "status": "placed",
        "estimated_delivery": <ISO datetime, now + 1 day>}``.

    Raises:
        RetryExhausted: If the delivery call fails on all retry attempts.
    """
    correlation_id = str(uuid4())
    care_recipient_id = _resolve_recipient_for_medication(medication_id)
    try:
        raw = await with_retry(
            _simulate_delivery_order,
            f"pharmacy delivery of {medication_id} from {pharmacy_id}",
        )
        result = {
            "order_id": raw["order_id"],
            "status": "placed",
            "estimated_delivery": raw["estimated_delivery"],
        }

        _audit(
            "order_pharmacy_delivery",
            care_recipient_id,
            f"Placed pharmacy delivery for {medication_id} from {pharmacy_id}",
            "success",
            correlation_id,
        )
        logger.info(
            "order_pharmacy_delivery: placed %s for %s via %s",
            result["order_id"], medication_id, pharmacy_id,
        )
        return result
    except Exception as e:
        _audit(
            "order_pharmacy_delivery",
            care_recipient_id,
            f"Pharmacy delivery for {medication_id} from {pharmacy_id} failed: {e}",
            "failure",
            correlation_id,
        )
        logger.error(
            "order_pharmacy_delivery failed for %s: %s", medication_id, e
        )
        raise


# ---------------------------------------------------------------------------
# MCP tool adapters + server
# ---------------------------------------------------------------------------

@tool(
    "check_delivery_status",
    "Check the status of a grocery or pharmacy delivery.",
    {"delivery_id": str},
)
async def _check_delivery_status_tool(args: dict) -> dict:
    """MCP adapter for :func:`check_delivery_status`.

    Args:
        args: MCP arguments dict; requires ``delivery_id``.

    Returns:
        MCP content-block envelope wrapping the DeliveryStatus dict.
    """
    return _mcp_result(check_delivery_status(args["delivery_id"]))


@tool(
    "order_grocery",
    "Place a grocery delivery order for a care recipient.",
    {"care_recipient_id": str, "items": list, "delivery_address": str},
)
async def _order_grocery_tool(args: dict) -> dict:
    """MCP adapter for :func:`order_grocery`.

    Args:
        args: MCP arguments dict; requires ``care_recipient_id``, ``items``,
            ``delivery_address``.

    Returns:
        MCP content-block envelope wrapping the order receipt.
    """
    return _mcp_result(
        await order_grocery(
            args["care_recipient_id"], args["items"], args["delivery_address"]
        )
    )


@tool(
    "order_pharmacy_delivery",
    "Place a pharmacy delivery order for a medication.",
    {"medication_id": str, "pharmacy_id": str, "delivery_address": str},
)
async def _order_pharmacy_delivery_tool(args: dict) -> dict:
    """MCP adapter for :func:`order_pharmacy_delivery`.

    Args:
        args: MCP arguments dict; requires ``medication_id``, ``pharmacy_id``,
            ``delivery_address``.

    Returns:
        MCP content-block envelope wrapping the order receipt.
    """
    return _mcp_result(
        await order_pharmacy_delivery(
            args["medication_id"], args["pharmacy_id"], args["delivery_address"]
        )
    )


delivery_server = create_sdk_mcp_server(
    name="delivery",
    version="1.0.0",
    tools=[
        _check_delivery_status_tool,
        _order_grocery_tool,
        _order_pharmacy_delivery_tool,
    ],
)
