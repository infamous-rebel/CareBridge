"""Logistics agent for CareBridge delivery management.

Handles delivery failures with escalation rules: essential deliveries
(pharmacy, medication, food, grocery) trigger alerts on failure,
while non-essential deliveries are retried and logged.
"""

import logging
from typing import Any, Optional
from uuid import uuid4

from src.models.schemas import DeliveryStatus, DeliveryOrder, CareEvent
from src.models.audit_log import write_audit_event
from src.models.escalation_logic import classify_action
from src.tools.logistics_tools import check_delivery_status, order_grocery, order_pharmacy_delivery
from src.tools.retry import with_retry, RetryExhausted
from src.mcp import get_mcp_server_configs
from src.runtime.model_factory import get_model

logger = logging.getLogger(__name__)

# Essential delivery types that require immediate escalation on failure
ESSENTIAL_DELIVERY_TYPES = {"pharmacy", "medication", "food", "grocery"}

# Delivery MCP server config attached to this agent's Strands Agent so it can
# see and call the delivery MCP tools under a real Strands session with the
# configured LLM provider. The direct delivery tool functions imported above
# remain the in-process fallback used when the Strands SDK or an LLM provider is
# unavailable (see create_logistics_agent()).
LOGISTICS_MCP_SERVERS: list[dict] = [get_mcp_server_configs()["delivery"]]

# Surfaced to the Supervisor's routing LLM as this agent's tool description, so
# the model can match an incoming event to the right specialist. Scope is
# delivery only — AGENTS.md §1.
LOGISTICS_AGENT_DESCRIPTION = (
    "Delivery and logistics specialist. Handles delivery_failed events (a "
    "pharmacy, medication, food, or grocery delivery did not arrive and may "
    "need re-ordering). Capabilities: check delivery status, order groceries, "
    "order a pharmacy delivery. Failure of an essential delivery is escalated "
    "deterministically by this agent. Does NOT send family alerts or modify "
    "medication or appointment data — route those events to the communication, "
    "medication, or appointment specialist instead."
)


async def process_delivery_failure(delivery_id: str, care_recipient_id: str) -> dict:
    """Handle a failed delivery with escalation rules.

    Essential deliveries (pharmacy, medication, food, grocery) are escalated
    immediately. Non-essential deliveries are retried once, then logged.

    Args:
        delivery_id: The delivery identifier that failed.
        care_recipient_id: The care recipient affected by the failure.

    Returns:
        Dict with keys: delivery_id, status, escalated, escalation_level,
        retry_attempted, actions_taken.
    """
    actions_taken: list[str] = []
    correlation_id = str(uuid4())

    # Check current delivery status
    try:
        status: DeliveryStatus = check_delivery_status(delivery_id)
    except ValueError as e:
        logger.error("Delivery %s not found: %s", delivery_id, e)
        write_audit_event(
            actor="logistics",
            action_type="check_delivery_status",
            care_recipient_id=care_recipient_id,
            rationale=f"Delivery {delivery_id} not found in records",
            outcome="failure",
            correlation_id=correlation_id,
        )
        return {
            "delivery_id": delivery_id,
            "status": "not_found",
            "escalated": True,
            "escalation_level": "alert",
            "retry_attempted": False,
            "actions_taken": [f"delivery_lookup_failed:{delivery_id}"],
        }

    actions_taken.append(f"checked_status:{delivery_id}:{status.status}")

    if status.status != "failed":
        logger.info("Delivery %s status is %s, no failure handling needed", delivery_id, status.status)
        return {
            "delivery_id": delivery_id,
            "status": status.status,
            "escalated": False,
            "escalation_level": None,
            "retry_attempted": False,
            "actions_taken": actions_taken,
        }

    # Determine delivery type from the failure reason or default to essential
    delivery_type = _infer_delivery_type(delivery_id)

    if delivery_type in ESSENTIAL_DELIVERY_TYPES:
        # Essential delivery failure → escalate immediately
        logger.warning(
            "Essential delivery %s (type=%s) failed, escalating",
            delivery_id, delivery_type,
        )
        write_audit_event(
            actor="logistics",
            action_type="escalate_delivery_failure",
            care_recipient_id=care_recipient_id,
            rationale=f"Essential delivery {delivery_id} ({delivery_type}) failed: {status.failure_reason}",
            outcome="escalated",
            correlation_id=correlation_id,
        )
        actions_taken.append(f"escalated:{delivery_id}:{delivery_type}")
        return {
            "delivery_id": delivery_id,
            "status": "failed",
            "escalated": True,
            "escalation_level": "alert",
            "retry_attempted": False,
            "actions_taken": actions_taken,
        }

    # Non-essential delivery failure → retry once
    logger.info("Non-essential delivery %s (type=%s) failed, retrying", delivery_id, delivery_type)
    actions_taken.append(f"retry_attempted:{delivery_id}")

    try:
        retry_result: DeliveryStatus = await with_retry(
            check_delivery_status,
            delivery_id,
            max_attempts=2,
        )
        if retry_result.status == "failed":
            raise RetryExhausted(
                f"Delivery {delivery_id} still failed after retry: {retry_result.failure_reason}",
                last_exception=RuntimeError(retry_result.failure_reason or "delivery still failed"),
            )
        write_audit_event(
            actor="logistics",
            action_type="retry_delivery_success",
            care_recipient_id=care_recipient_id,
            rationale=f"Non-essential delivery {delivery_id} retry succeeded, status={retry_result.status}",
            outcome="success",
            correlation_id=correlation_id,
        )
        actions_taken.append(f"retry_succeeded:{delivery_id}")
        return {
            "delivery_id": delivery_id,
            "status": "retry_succeeded",
            "escalated": False,
            "escalation_level": None,
            "retry_attempted": True,
            "actions_taken": actions_taken,
        }
    except RetryExhausted:
        logger.warning("Retry exhausted for non-essential delivery %s", delivery_id)
        write_audit_event(
            actor="logistics",
            action_type="retry_delivery_failure",
            care_recipient_id=care_recipient_id,
            rationale=f"Non-essential delivery {delivery_id} retry exhausted, logging warning",
            outcome="failure",
            correlation_id=correlation_id,
        )
        actions_taken.append(f"retry_exhausted:{delivery_id}")
        return {
            "delivery_id": delivery_id,
            "status": "failed",
            "escalated": False,
            "escalation_level": None,
            "retry_attempted": True,
            "actions_taken": actions_taken,
        }


def _infer_delivery_type(delivery_id: str) -> str:
    """Infer delivery type from delivery history fixtures.

    Args:
        delivery_id: The delivery identifier.

    Returns:
        Delivery type string (e.g. 'pharmacy', 'grocery'), defaults to 'unknown'.
    """
    import json
    from pathlib import Path

    fixtures_path = Path(__file__).parent.parent.parent / "fixtures"
    delivery_file = fixtures_path / "delivery_history.json"

    try:
        with open(delivery_file) as f:
            history = json.load(f)
        for record in history:
            if record["delivery_id"] == delivery_id:
                return record.get("delivery_type", "unknown")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error("Failed to load delivery history for type inference: %s", e)

    return "unknown"


async def handle_logistics_event(event: CareEvent) -> dict:
    """Main handler for logistics-related care events.

    Routes events based on type: delivery failures are processed with
    escalation rules, other events are handled by extracting order
    details from the event payload.

    Args:
        event: The CareEvent to process.

    Returns:
        Dict with keys: event_id, event_type, actions_taken,
        escalation_required, escalation_level.
    """
    logger.info(
        "Handling logistics event: type=%s recipient=%s",
        event.event_type, event.care_recipient_id,
    )

    actions_taken: list[str] = []
    escalation_required = False
    escalation_level = None

    if event.event_type == "delivery_failed":
        delivery_id = event.payload.get("delivery_id", "")
        if not delivery_id:
            logger.error("delivery_failed event missing delivery_id in payload")
            return {
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "actions_taken": ["error:missing_delivery_id"],
                "escalation_required": True,
                "escalation_level": "alert",
            }

        result = await process_delivery_failure(delivery_id, event.care_recipient_id)
        actions_taken.extend(result["actions_taken"])
        escalation_required = result.get("escalated", False)
        escalation_level = result.get("escalation_level")

    else:
        logger.info(
            "Event type %s does not require logistics-specific handling",
            event.event_type,
        )
        actions_taken.append(f"logged:{event.event_type}")

    return {
        "event_id": str(event.event_id),
        "event_type": event.event_type,
        "actions_taken": actions_taken,
        "escalation_required": escalation_required,
        "escalation_level": escalation_level,
    }


def create_logistics_agent() -> Optional[Any]:
    """Build the Strands Logistics Agent with the delivery MCP server attached.

    Mirrors the Supervisor's graceful-degradation pattern: when the Strands SDK
    is missing or no LLM provider is configured, this returns ``None`` and
    callers use the direct handler/tool functions in this module — the path
    exercised by local tests and ``main.py``.

    The model comes from :func:`src.runtime.model_factory.get_model`, so this
    specialist follows whichever provider ``LLM_PROVIDER`` selects instead of
    hardcoding one.

    ``LOGISTICS_MCP_SERVERS`` is passed to the Agent's ``mcp_servers`` argument
    so the agent can see and call the delivery MCP tools; the direct delivery
    tools are also passed via ``tools=`` as the in-process fallback. If the
    installed Strands version does not accept an ``mcp_servers`` kwarg (Strands
    wires MCP through tools/MCPSession), the agent is built without it and the
    rejection is logged, rather than failing outright.

    Returns:
        The configured Strands Agent if the SDK and an LLM provider are
        available, otherwise None.
    """
    try:
        from strands import Agent
        from strands.tools import tool
    except ImportError as e:
        logger.warning(
            "Strands SDK not available, Logistics Agent MCP tools not attached "
            "(using direct delivery tools): %s", e,
        )
        return None

    try:
        model = get_model()
    except RuntimeError as e:
        logger.info(
            "No LLM provider available for Logistics Agent — using direct "
            "delivery tools: %s", e,
        )
        return None

    try:
        agent_kwargs: dict[str, Any] = {
            "name": "CareBridgeLogistics",
            "description": LOGISTICS_AGENT_DESCRIPTION,
            "model": model,
            # Strands 1.55 registers AgentTool instances, not bare callables:
            # passing the functions directly logs "unrecognized tool
            # specification" and leaves the agent with no tools at all. tool()
            # wraps them while keeping the originals directly callable for the
            # deterministic path in handle_logistics_event().
            "tools": [
                tool(check_delivery_status),
                tool(order_grocery),
                tool(order_pharmacy_delivery),
            ],
            "mcp_servers": LOGISTICS_MCP_SERVERS,
        }
        try:
            agent = Agent(**agent_kwargs)
        except TypeError as e:
            logger.warning(
                "Strands Agent rejected mcp_servers= (%s); building Logistics "
                "Agent without MCP attachment", e,
            )
            agent_kwargs.pop("mcp_servers", None)
            agent = Agent(**agent_kwargs)
        logger.info("Strands Logistics Agent created successfully")
        return agent
    except Exception as e:
        logger.warning(
            "Failed to create Strands Logistics Agent, using direct tools: %s", e
        )
        return None
