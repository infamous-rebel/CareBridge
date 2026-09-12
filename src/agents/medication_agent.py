"""CareBridge Medication Agent — pharmacy coordination.

Handles medication-related events: refill checks, refill ordering with retry,
and adherence pattern detection. All actions are audit-trailed.
"""

import logging
from typing import Any, Optional

from src.models.schemas import RefillStatus, RefillOrder, AdherencePattern, CareEvent
from src.models.escalation_logic import classify_action
from src.tools.medication_tools import (
    check_refill_status,
    order_refill,
    detect_adherence_pattern,
)
from src.tools.retry import with_retry, RetryExhausted
from src.mcp import get_mcp_server_configs
from src.runtime.model_factory import get_model

logger = logging.getLogger(__name__)

DEFAULT_REFILL_THRESHOLD = 5

# Pharmacy MCP server config attached to this agent's Strands Agent so it can
# see and call the pharmacy MCP tools under a real Strands session with the
# configured LLM provider. The direct pharmacy tool functions imported above
# remain the in-process fallback used when the Strands SDK or an LLM provider is
# unavailable (see create_medication_agent()).
MEDICATION_MCP_SERVERS: list[dict] = [get_mcp_server_configs()["pharmacy"]]

# Surfaced to the Supervisor's routing LLM as this agent's tool description, so
# the model can match an incoming event to the right specialist (SPEC: routing
# is the model's decision, and a description-less tool cannot be chosen
# intelligently). Scope is pharmacy only — AGENTS.md §1.
MEDICATION_AGENT_DESCRIPTION = (
    "Medication and pharmacy specialist. Handles refill_low events (a "
    "medication is running low and needs a refill order) and "
    "adherence_deviation events (missed or off-schedule doses). Capabilities: "
    "check refill status, order a pharmacy refill, detect adherence patterns. "
    "Does NOT schedule appointments, arrange deliveries, or message family "
    "members — route those events to the appointment, logistics, or "
    "communication specialist instead."
)


async def handle_medication_event(event: CareEvent) -> dict:
    """Main entry point for the Medication Agent, called by the Supervisor.

    Processes a CareEvent by checking refill status, ordering refills when
    eligible, and detecting adherence deviations. Returns a structured result
    dict describing all actions taken and any escalation requirements.

    Args:
        event: The CareEvent to process. Payload must contain "medication_id".

    Returns:
        A dict with keys:
            - medication_id: the medication processed
            - actions_taken: list of action description strings
            - escalation_required: bool
            - escalation_level: "info" | "alert" | "emergency" | None
            - refill_status: RefillStatus model dump (if applicable)
            - refill_order: RefillOrder model dump (if applicable)
            - adherence: AdherencePattern model dump (if applicable)
    """
    medication_id: str = event.payload.get("medication_id", "")
    if not medication_id:
        logger.error("handle_medication_event called without medication_id in payload")
        return {
            "medication_id": None,
            "actions_taken": ["error: missing medication_id in event payload"],
            "escalation_required": False,
            "escalation_level": None,
        }

    actions_taken: list[str] = []
    escalation_required: bool = False
    escalation_level: str | None = None

    # Step 1: Check refill status
    try:
        status: RefillStatus = check_refill_status(medication_id)
        actions_taken.append(
            f"Checked refill status for {medication_id}: "
            f"{status.days_remaining} days remaining"
        )
    except ValueError as e:
        logger.error(f"Failed to check refill status: {e}")
        return {
            "medication_id": medication_id,
            "actions_taken": [f"error: {e}"],
            "escalation_required": False,
            "escalation_level": None,
        }

    # Step 2: Order refill if eligible
    refill_order: RefillOrder | None = None
    if status.days_remaining <= DEFAULT_REFILL_THRESHOLD and status.refill_eligible:
        try:
            refill_order = await process_refill(
                medication_id, status.pharmacy_id
            )
            if refill_order.status == "placed":
                actions_taken.append(
                    f"Ordered refill for {medication_id}: "
                    f"order_id={refill_order.order_id}"
                )
            else:
                actions_taken.append(
                    f"Refill order failed for {medication_id}: "
                    f"{refill_order.failure_reason}"
                )
        except RetryExhausted as e:
            logger.error(
                f"Refill order exhausted retries for {medication_id}: {e}"
            )
            escalation_required = True
            escalation_level = "alert"
            actions_taken.append(
                f"Refill order failed after retries for {medication_id} — "
                f"escalation required"
            )

    # Step 3: Detect adherence pattern
    try:
        adherence: AdherencePattern = check_and_flag_adherence(medication_id)
        actions_taken.append(
            f"Adherence check for {medication_id}: "
            f"deviation={adherence.deviation_flag}, severity={adherence.severity}"
        )
    except ValueError as e:
        logger.error(f"Failed to check adherence: {e}")
        adherence = None  # type: ignore[assignment]
        actions_taken.append(f"Adherence check failed for {medication_id}: {e}")

    # Step 4: Evaluate adherence deviation for escalation
    if (
        adherence is not None
        and adherence.deviation_flag
        and adherence.severity in ("moderate", "severe")
    ):
        escalation_required = True
        escalation_level = "alert"
        actions_taken.append(
            f"Adherence deviation detected for {medication_id} "
            f"(severity={adherence.severity}) — family alert needed"
        )

    return {
        "medication_id": medication_id,
        "actions_taken": actions_taken,
        "escalation_required": escalation_required,
        "escalation_level": escalation_level,
        "refill_status": status.model_dump(),
        "refill_order": refill_order.model_dump() if refill_order else None,
        "adherence": adherence.model_dump() if adherence else None,
    }


async def process_refill(medication_id: str, pharmacy_id: str) -> RefillOrder:
    """Order a medication refill with retry logic and audit trail.

    Wraps order_refill with the shared with_retry() helper (3 attempts,
    exponential backoff). Audit events are written inside order_refill itself.

    Args:
        medication_id: The medication to refill.
        pharmacy_id: The pharmacy to order from.

    Returns:
        RefillOrder with the order result.

    Raises:
        RetryExhausted: If all retry attempts fail.
    """
    logger.info(
        f"Processing refill for {medication_id} at pharmacy {pharmacy_id}"
    )
    result: RefillOrder = await with_retry(
        order_refill, medication_id, pharmacy_id
    )
    return result


def check_and_flag_adherence(medication_id: str) -> AdherencePattern:
    """Check adherence and determine if alerting is needed.

    Synchronous wrapper around detect_adherence_pattern that also logs
    whether the result requires caregiver alerting.

    Args:
        medication_id: The medication to analyze.

    Returns:
        AdherencePattern with deviation analysis.

    Raises:
        ValueError: If medication_id not found in fixtures.
    """
    pattern: AdherencePattern = detect_adherence_pattern(medication_id)

    if pattern.deviation_flag and pattern.severity in ("moderate", "severe"):
        logger.warning(
            f"Adherence alert for {medication_id}: "
            f"missed={pattern.missed_doses}, late={pattern.late_doses}, "
            f"severity={pattern.severity}"
        )
    else:
        logger.info(f"Adherence OK for {medication_id}")

    return pattern


def create_medication_agent() -> Optional[Any]:
    """Build the Strands Medication Agent with the pharmacy MCP server attached.

    Mirrors the Supervisor's graceful-degradation pattern: when the Strands SDK
    is missing or no LLM provider is configured, this returns ``None`` and
    callers use the direct handler/tool functions in this module — the path
    exercised by local tests and ``main.py``.

    The model comes from :func:`src.runtime.model_factory.get_model`, so this
    specialist follows whichever provider ``LLM_PROVIDER`` selects instead of
    hardcoding one.

    ``MEDICATION_MCP_SERVERS`` is passed to the Agent's ``mcp_servers`` argument
    so the agent can see and call the pharmacy MCP tools; the direct pharmacy
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
            "Strands SDK not available, Medication Agent MCP tools not attached "
            "(using direct pharmacy tools): %s", e,
        )
        return None

    try:
        model = get_model()
    except RuntimeError as e:
        logger.info(
            "No LLM provider available for Medication Agent — using direct "
            "pharmacy tools: %s", e,
        )
        return None

    try:
        agent_kwargs: dict[str, Any] = {
            "name": "CareBridgeMedication",
            "description": MEDICATION_AGENT_DESCRIPTION,
            "model": model,
            # Strands 1.55 registers AgentTool instances, not bare callables:
            # passing the functions directly logs "unrecognized tool
            # specification" and leaves the agent with no tools at all. tool()
            # wraps them while keeping the originals directly callable for the
            # deterministic path in handle_medication_event().
            "tools": [
                tool(check_refill_status),
                tool(order_refill),
                tool(detect_adherence_pattern),
            ],
            "mcp_servers": MEDICATION_MCP_SERVERS,
        }
        try:
            agent = Agent(**agent_kwargs)
        except TypeError as e:
            logger.warning(
                "Strands Agent rejected mcp_servers= (%s); building Medication "
                "Agent without MCP attachment", e,
            )
            agent_kwargs.pop("mcp_servers", None)
            agent = Agent(**agent_kwargs)
        logger.info("Strands Medication Agent created successfully")
        return agent
    except Exception as e:
        logger.warning(
            "Failed to create Strands Medication Agent, using direct tools: %s", e
        )
        return None
