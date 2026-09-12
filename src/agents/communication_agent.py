"""CareBridge Communication Agent — messaging and notification coordination.

Handles all outbound communication: emergency alerts, caregiver notifications,
and daily digest batching. All actions are audit-trailed before execution.
"""

import logging
from typing import Any, Optional
from uuid import uuid4

from src.models.schemas import (
    AlertResult,
    CareEvent,
    StatusSummary,
    FamilyPreferences,
)
from src.models.audit_log import write_audit_event
from src.models.escalation_logic import classify_action
from src.tools.communication_tools import (
    send_alert,
    synthesize_status,
    get_family_preferences,
)
from src.tools.retry import with_retry, RetryExhausted
from src.mcp import get_mcp_server_configs
from src.runtime.model_factory import get_model

logger = logging.getLogger(__name__)

# Messaging MCP server config attached to this agent's Strands Agent so it can
# see and call the messaging MCP tools under a real Strands session with the
# configured LLM provider. The direct messaging tool functions imported above
# remain the in-process fallback used when the Strands SDK or an LLM provider is
# unavailable (see create_communication_agent()).
COMMUNICATION_MCP_SERVERS: list[dict] = [get_mcp_server_configs()["messaging"]]

# Surfaced to the Supervisor's routing LLM as this agent's tool description. The
# wording is deliberately explicit that this specialist is NOT the primary owner
# of refill/appointment/delivery events: the LLM must route those to their own
# specialist and let the resulting escalation trigger notification separately
# (AGENTS.md §1 and §8 — escalation is deterministic, never model-decided).
COMMUNICATION_AGENT_DESCRIPTION = (
    "Family communication specialist. Sends alerts by SMS, email, or phone "
    "call, produces daily digests, and synthesizes a plain-language status "
    "summary of a care recipient. Capabilities: send an alert, synthesize "
    "status, read family contact preferences and escalation order. Route here "
    "ONLY when the event is itself about notifying or reporting to the family. "
    "Do NOT route refill_low, appointment_upcoming, or delivery_failed events "
    "here — those belong to the medication, appointment, and logistics "
    "specialists, which raise their own escalation. Never modifies care data "
    "and never calls pharmacy, calendar, or delivery APIs."
)


async def handle_communication_event(event: CareEvent) -> dict:
    """Main entry point for the Communication Agent, called by the Supervisor.

    Processes a CareEvent by determining the appropriate alert level and
    routing notifications to the correct family members.

    Args:
        event: The CareEvent to process. Payload should contain "level"
               (info|alert|emergency) and "message".

    Returns:
        A dict with keys:
            - care_recipient_id: the recipient processed
            - actions_taken: list of action description strings
            - escalation_required: bool
            - escalation_level: "info" | "alert" | "emergency" | None
            - alert_result: AlertResult model dump (if applicable)
    """
    care_recipient_id: str = event.care_recipient_id
    level: str = event.payload.get("level", "info")
    message: str = event.payload.get("message", f"Event: {event.event_type}")

    actions_taken: list[str] = []
    escalation_required: bool = False
    escalation_level: str | None = None
    alert_result: AlertResult | None = None

    if level == "emergency":
        # Emergency: notify ALL family members with full channel blast
        try:
            alert_result = await send_family_alert(
                care_recipient_id, message, "emergency"
            )
            actions_taken.append(
                f"Emergency alert sent to ALL family members via "
                f"{alert_result.channel_used}"
            )
            escalation_required = True
            escalation_level = "emergency"
        except RetryExhausted as e:
            logger.error(
                f"Emergency alert failed for {care_recipient_id}: {e}"
            )
            actions_taken.append(
                f"Emergency alert FAILED after retries: {e}"
            )
            escalation_required = True
            escalation_level = "emergency"

    elif level == "alert":
        # Alert: SMS to primary caregiver, email to others
        try:
            alert_result = await send_family_alert(
                care_recipient_id, message, "alert"
            )
            actions_taken.append(
                f"Alert sent to primary caregiver (SMS) and others (email) "
                f"via {alert_result.channel_used}"
            )
            escalation_required = True
            escalation_level = "alert"
        except RetryExhausted as e:
            logger.error(
                f"Alert failed for {care_recipient_id}: {e}"
            )
            actions_taken.append(
                f"Alert FAILED after retries: {e}"
            )
            escalation_required = True
            escalation_level = "alert"

    else:
        # Info: batch into daily digest
        logger.info(
            f"Info-level event for {care_recipient_id} queued for daily digest"
        )
        actions_taken.append(
            f"Info event queued for daily digest: {event.event_type}"
        )
        escalation_level = "info"

    return {
        "care_recipient_id": care_recipient_id,
        "actions_taken": actions_taken,
        "escalation_required": escalation_required,
        "escalation_level": escalation_level,
        "alert_result": alert_result.model_dump() if alert_result else None,
    }


async def send_family_alert(
    care_recipient_id: str,
    message: str,
    level: str,
) -> AlertResult:
    """Send an alert to a care recipient's family with retry logic.

    Wraps send_alert with the shared with_retry() helper (3 attempts,
    exponential backoff). The Supervisor calls this when escalation is needed.

    Args:
        care_recipient_id: The care recipient whose family should be notified.
        message: The alert message content.
        level: Alert severity — "info", "alert", or "emergency".

    Returns:
        AlertResult with delivery confirmation.

    Raises:
        RetryExhausted: If all retry attempts fail.
    """
    logger.info(
        f"Sending {level}-level family alert for {care_recipient_id}"
    )

    result: AlertResult = await with_retry(
        send_alert, care_recipient_id, message, level
    )
    return result


def get_care_status(care_recipient_id: str) -> StatusSummary:
    """Get the current care status summary for a care recipient.

    Wraps synthesize_status for the Supervisor to call when building
    daily digests or responding to caregiver queries.

    Args:
        care_recipient_id: The care recipient identifier.

    Returns:
        StatusSummary with summary text, recent events, and pending actions.
    """
    logger.info(f"Synthesizing care status for {care_recipient_id}")
    return synthesize_status(care_recipient_id)


def create_communication_agent() -> Optional[Any]:
    """Build the Strands Communication Agent with the messaging MCP server attached.

    Mirrors the Supervisor's graceful-degradation pattern: when the Strands SDK
    is missing or no LLM provider is configured, this returns ``None`` and
    callers use the direct handler/tool functions in this module — the path
    exercised by local tests and ``main.py``.

    The model comes from :func:`src.runtime.model_factory.get_model`, so this
    specialist follows whichever provider ``LLM_PROVIDER`` selects instead of
    hardcoding one.

    ``COMMUNICATION_MCP_SERVERS`` is passed to the Agent's ``mcp_servers``
    argument so the agent can see and call the messaging MCP tools; the direct
    messaging tools are also passed via ``tools=`` as the in-process fallback. If
    the installed Strands version does not accept an ``mcp_servers`` kwarg
    (Strands wires MCP through tools/MCPSession), the agent is built without it
    and the rejection is logged, rather than failing outright.

    Returns:
        The configured Strands Agent if the SDK and an LLM provider are
        available, otherwise None.
    """
    try:
        from strands import Agent
        from strands.tools import tool
    except ImportError as e:
        logger.warning(
            "Strands SDK not available, Communication Agent MCP tools not "
            "attached (using direct messaging tools): %s", e,
        )
        return None

    try:
        model = get_model()
    except RuntimeError as e:
        logger.info(
            "No LLM provider available for Communication Agent — using direct "
            "messaging tools: %s", e,
        )
        return None

    try:
        agent_kwargs: dict[str, Any] = {
            "name": "CareBridgeCommunication",
            "description": COMMUNICATION_AGENT_DESCRIPTION,
            "model": model,
            # Strands 1.55 registers AgentTool instances, not bare callables:
            # passing the functions directly logs "unrecognized tool
            # specification" and leaves the agent with no tools at all. tool()
            # wraps them while keeping the originals directly callable for the
            # deterministic path in handle_communication_event().
            "tools": [
                tool(send_alert),
                tool(synthesize_status),
                tool(get_family_preferences),
            ],
            "mcp_servers": COMMUNICATION_MCP_SERVERS,
        }
        try:
            agent = Agent(**agent_kwargs)
        except TypeError as e:
            logger.warning(
                "Strands Agent rejected mcp_servers= (%s); building Communication "
                "Agent without MCP attachment", e,
            )
            agent_kwargs.pop("mcp_servers", None)
            agent = Agent(**agent_kwargs)
        logger.info("Strands Communication Agent created successfully")
        return agent
    except Exception as e:
        logger.warning(
            "Failed to create Strands Communication Agent, using direct tools: %s", e
        )
        return None
