"""Appointment Agent for CareBridge.

Handles appointment-related care events: checks upcoming appointments,
sends prep checklists, and flags transportation needs for logistics
coordination. All actions are audit-trailed and follow the escalation
rules defined in AGENTS.md.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from src.models.schemas import Appointment, CareEvent, ChecklistResult
from src.models.audit_log import write_audit_event
from src.models.escalation_logic import classify_action
from src.tools.appointment_tools import get_calendar, schedule_appointment, send_prep_checklist
from src.tools.retry import with_retry, RetryExhausted
from src.mcp import get_mcp_server_configs
from src.runtime.model_factory import get_model

logger = logging.getLogger(__name__)

_FORTY_EIGHT_HOURS = timedelta(hours=48)
_SEVEN_DAYS = timedelta(days=7)

# Calendar MCP server config attached to this agent's Strands Agent so it can
# see and call the calendar MCP tools under a real Strands session with the
# configured LLM provider. The direct calendar tool functions imported above
# remain the in-process fallback used when the Strands SDK or an LLM provider is
# unavailable (see create_appointment_agent()).
APPOINTMENT_MCP_SERVERS: list[dict] = [get_mcp_server_configs()["calendar"]]

# Surfaced to the Supervisor's routing LLM as this agent's tool description, so
# the model can match an incoming event to the right specialist. Scope is
# calendar only — AGENTS.md §1.
APPOINTMENT_AGENT_DESCRIPTION = (
    "Appointment and calendar specialist. Handles appointment_upcoming events "
    "(a scheduled appointment is approaching and needs confirmation, "
    "reminders, or preparation). Capabilities: read the care calendar, schedule "
    "an appointment, send the appointment preparation checklist. Does NOT order "
    "medication refills, arrange deliveries, or send family alerts — route "
    "those events to the medication, logistics, or communication specialist "
    "instead."
)


def check_upcoming_appointments(care_recipient_id: str) -> list[dict]:
    """Return appointments needing attention within the near-term window.

    An appointment needs attention if it is within 48 hours of now
    (requires prep checklist) or within 7 days and has
    transportation_needed=True (requires logistics coordination).

    Args:
        care_recipient_id: The care recipient identifier.

    Returns:
        List of dicts, each with keys:
            - appointment (Appointment): the appointment model
            - needs_checklist (bool): within 48h → send prep checklist
            - needs_transport (bool): within 7d and transportation_needed=True
    """
    now = datetime.now(timezone.utc)

    try:
        appointments = get_calendar(care_recipient_id, horizon_days=7)
    except ValueError:
        logger.warning(
            "check_upcoming_appointments: no appointments for %s",
            care_recipient_id,
        )
        return []

    results: list[dict] = []
    for appt in appointments:
        appt_dt = appt.datetime
        if appt_dt.tzinfo is None:
            appt_dt = appt_dt.replace(tzinfo=timezone.utc)

        time_until = appt_dt - now
        needs_checklist = timedelta(0) <= time_until <= _FORTY_EIGHT_HOURS
        needs_transport = (
            timedelta(0) <= time_until <= _SEVEN_DAYS and appt.transportation_needed
        )

        if needs_checklist or needs_transport:
            results.append({
                "appointment": appt,
                "needs_checklist": needs_checklist,
                "needs_transport": needs_transport,
            })

    return results


async def handle_appointment_event(event: CareEvent) -> dict:
    """Handle an appointment-related care event end-to-end.

    Orchestrates the following:
      1. Retrieves the care recipient's calendar.
      2. For each upcoming appointment within 48 hours, sends a prep checklist.
      3. For each appointment within 7 days requiring transportation, flags
         logistics coordination.
      4. Returns a structured result summarising all actions taken.

    Args:
        event: The incoming CareEvent (expected event_type="appointment_upcoming").

    Returns:
        A dict with keys:
            - care_recipient_id (str)
            - actions_taken (list[str]): human-readable action descriptions
            - logistics_coordination_needed (bool): True if any appointment needs transport
            - checklists_sent (list[str]): appointment_ids that received a checklist
            - transport_appointments (list[str]): appointment_ids needing transport
    """
    care_recipient_id = event.care_recipient_id
    actions_taken: list[str] = []
    checklists_sent: list[str] = []
    transport_appointments: list[str] = []
    logistics_coordination_needed = False

    logger.info(
        "handle_appointment_event: processing event %s for recipient %s",
        event.event_id, care_recipient_id,
    )

    # Step 1: Retrieve the calendar
    try:
        appointments = get_calendar(care_recipient_id, horizon_days=7)
        actions_taken.append(
            f"Retrieved calendar: {len(appointments)} appointments in next 7 days"
        )
    except ValueError as exc:
        logger.warning(
            "handle_appointment_event: %s", exc,
        )
        return {
            "care_recipient_id": care_recipient_id,
            "actions_taken": [f"No appointments found: {exc}"],
            "logistics_coordination_needed": False,
            "checklists_sent": [],
            "transport_appointments": [],
        }

    now = datetime.now(timezone.utc)

    # Step 2 & 3: Evaluate each appointment
    for appt in appointments:
        appt_dt = appt.datetime
        if appt_dt.tzinfo is None:
            appt_dt = appt_dt.replace(tzinfo=timezone.utc)

        time_until = appt_dt - now

        # Within 48 hours → send prep checklist
        if timedelta(0) <= time_until <= _FORTY_EIGHT_HOURS:
            try:
                result: ChecklistResult = send_prep_checklist(appt.appointment_id)
                checklists_sent.append(appt.appointment_id)
                actions_taken.append(
                    f"Sent prep checklist for appointment {appt.appointment_id} "
                    f"({appt.provider_name}, {appt.specialty})"
                )
            except ValueError as exc:
                logger.error(
                    "Failed to send checklist for %s: %s",
                    appt.appointment_id, exc,
                )
                actions_taken.append(
                    f"Failed to send checklist for {appt.appointment_id}: {exc}"
                )

        # Within 7 days AND transportation needed → flag for logistics
        if timedelta(0) <= time_until <= _SEVEN_DAYS and appt.transportation_needed:
            logistics_coordination_needed = True
            transport_appointments.append(appt.appointment_id)
            actions_taken.append(
                f"Logistics coordination needed for appointment {appt.appointment_id} "
                f"({appt.provider_name}, {appt.location})"
            )

    logger.info(
        "handle_appointment_event: completed for %s — %d actions, %d checklists, %d transport",
        care_recipient_id, len(actions_taken), len(checklists_sent), len(transport_appointments),
    )

    return {
        "care_recipient_id": care_recipient_id,
        "actions_taken": actions_taken,
        "logistics_coordination_needed": logistics_coordination_needed,
        "checklists_sent": checklists_sent,
        "transport_appointments": transport_appointments,
    }


def create_appointment_agent() -> Optional[Any]:
    """Build the Strands Appointment Agent with the calendar MCP server attached.

    Mirrors the Supervisor's graceful-degradation pattern: when the Strands SDK
    is missing or no LLM provider is configured, this returns ``None`` and
    callers use the direct handler/tool functions in this module — the path
    exercised by local tests and ``main.py``.

    The model comes from :func:`src.runtime.model_factory.get_model`, so this
    specialist follows whichever provider ``LLM_PROVIDER`` selects instead of
    hardcoding one.

    ``APPOINTMENT_MCP_SERVERS`` is passed to the Agent's ``mcp_servers`` argument
    so the agent can see and call the calendar MCP tools; the direct calendar
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
            "Strands SDK not available, Appointment Agent MCP tools not attached "
            "(using direct calendar tools): %s", e,
        )
        return None

    try:
        model = get_model()
    except RuntimeError as e:
        logger.info(
            "No LLM provider available for Appointment Agent — using direct "
            "calendar tools: %s", e,
        )
        return None

    try:
        agent_kwargs: dict[str, Any] = {
            "name": "CareBridgeAppointment",
            "description": APPOINTMENT_AGENT_DESCRIPTION,
            "model": model,
            # Strands 1.55 registers AgentTool instances, not bare callables:
            # passing the functions directly logs "unrecognized tool
            # specification" and leaves the agent with no tools at all. tool()
            # wraps them while keeping the originals directly callable for the
            # deterministic path in handle_appointment_event().
            "tools": [
                tool(get_calendar),
                tool(schedule_appointment),
                tool(send_prep_checklist),
            ],
            "mcp_servers": APPOINTMENT_MCP_SERVERS,
        }
        try:
            agent = Agent(**agent_kwargs)
        except TypeError as e:
            logger.warning(
                "Strands Agent rejected mcp_servers= (%s); building Appointment "
                "Agent without MCP attachment", e,
            )
            agent_kwargs.pop("mcp_servers", None)
            agent = Agent(**agent_kwargs)
        logger.info("Strands Appointment Agent created successfully")
        return agent
    except Exception as e:
        logger.warning(
            "Failed to create Strands Appointment Agent, using direct tools: %s", e
        )
        return None
