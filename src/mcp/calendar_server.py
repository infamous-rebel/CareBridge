"""CareBridge Calendar MCP server — in-process mock of the calendar API.

SPEC.md §6.4 specifies Calendar as an *external SSE* MCP server backed by the
Qoder Google Calendar Connector. That connector is a Day-2 swap; per the spec's
documented fallback ("If connector unavailable, use in-process mock") this
module ships the in-process mock first so the system and its tests run without
external credentials. Swapping to SSE later is a transport-only change: the tool
names, signatures, and return shapes below are the stable contract.

Runs in-process via the Qoder Agent SDK's ``create_sdk_mcp_server`` / ``@tool``
helpers and backs the Appointment Agent with two tools:

* ``get_calendar(care_recipient_id, horizon_days=30)`` — upcoming appointments
* ``schedule_appointment(provider_id, care_recipient_id, preferred_datetime)`` —
  confirm a new appointment

Data source: ``fixtures/appointments.json``. Every tool call writes exactly one
audit event (actor="appointment").

As in the other servers, each tool is a typed business function (the SPEC
contract) plus a thin ``@tool`` async adapter bridging the Qoder SDK's
``async def handler(args: dict) -> dict`` convention.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from qoder_agent_sdk import create_sdk_mcp_server, tool

from src.models.audit_log import write_audit_event
from src.models.schemas import Appointment

logger = logging.getLogger(__name__)

FIXTURES_PATH = Path(__file__).parent.parent.parent / "fixtures"

# Audit actor for every tool on this server (AGENTS.md §7).
_ACTOR = "appointment"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_appointments() -> list[dict]:
    """Load appointment fixtures from ``fixtures/appointments.json``.

    Returns:
        List of raw appointment dictionaries.

    Raises:
        FileNotFoundError: If the fixtures file is missing.
        json.JSONDecodeError: If the fixtures file contains invalid JSON.
    """
    with open(FIXTURES_PATH / "appointments.json") as f:
        return json.load(f)


def _audit(
    action_type: str,
    care_recipient_id: str,
    rationale: str,
    outcome: str,
    correlation_id: str,
) -> None:
    """Write one calendar audit event (actor="appointment").

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

def get_calendar(care_recipient_id: str, horizon_days: int = 30) -> list[dict]:
    """Get upcoming appointments for a care recipient.

    Args:
        care_recipient_id: The care recipient identifier.
        horizon_days: Number of days to look ahead from now (default 30).

    Returns:
        List of Appointment dicts (appointment_id, provider_name, specialty,
        datetime, location, prep_required, transportation_needed,
        care_recipient_id) falling within ``[now, now + horizon_days]``.
        Empty list if there are none in the horizon.

    Raises:
        FileNotFoundError: If the fixtures file is missing.
        json.JSONDecodeError: If the fixtures file contains invalid JSON.
        ValueError: If an appointment datetime cannot be parsed.
    """
    correlation_id = str(uuid4())
    try:
        raw_appointments = _load_appointments()
        now = datetime.now(timezone.utc)
        horizon_end = now + timedelta(days=horizon_days)

        results: list[dict] = []
        for appt in raw_appointments:
            if appt.get("care_recipient_id") != care_recipient_id:
                continue
            appt_dt = datetime.fromisoformat(
                appt["datetime"].replace("Z", "+00:00")
            )
            if now <= appt_dt <= horizon_end:
                results.append(Appointment(**appt).model_dump(mode="json"))

        _audit(
            "get_calendar",
            care_recipient_id,
            f"Retrieved calendar for {care_recipient_id}: "
            f"{len(results)} appointment(s) within {horizon_days} day(s)",
            "success",
            correlation_id,
        )
        logger.info(
            "get_calendar: %d appointment(s) for %s within %d day(s)",
            len(results), care_recipient_id, horizon_days,
        )
        return results
    except Exception as e:
        _audit(
            "get_calendar",
            care_recipient_id,
            f"Calendar retrieval failed for {care_recipient_id}: {e}",
            "failure",
            correlation_id,
        )
        logger.error("get_calendar failed for %s: %s", care_recipient_id, e)
        raise


def schedule_appointment(
    provider_id: str,
    care_recipient_id: str,
    preferred_datetime: str,
) -> dict:
    """Schedule a new appointment with a provider.

    Mock implementation that confirms the requested slot. On Day 2 this becomes
    a call to the Google Calendar SSE connector; the return contract is stable.

    Args:
        provider_id: The healthcare provider identifier.
        care_recipient_id: The care recipient identifier.
        preferred_datetime: Requested appointment datetime (ISO 8601 string).

    Returns:
        Dict ``{"appointment_id": <UUID>, "status": "confirmed",
        "datetime": preferred_datetime}``.

    Raises:
        Exception: Re-raised after a failure audit event if confirmation fails.
    """
    correlation_id = str(uuid4())
    try:
        appointment_id = str(uuid4())
        result = {
            "appointment_id": appointment_id,
            "status": "confirmed",
            "datetime": preferred_datetime,
        }

        _audit(
            "schedule_appointment",
            care_recipient_id,
            f"Scheduled appointment {appointment_id} with provider "
            f"{provider_id} for {care_recipient_id}",
            "success",
            correlation_id,
        )
        logger.info(
            "schedule_appointment: confirmed %s with provider %s for %s",
            appointment_id, provider_id, care_recipient_id,
        )
        return result
    except Exception as e:
        _audit(
            "schedule_appointment",
            care_recipient_id,
            f"Failed to schedule appointment with provider {provider_id}: {e}",
            "failure",
            correlation_id,
        )
        logger.error(
            "schedule_appointment failed for %s via %s: %s",
            care_recipient_id, provider_id, e,
        )
        raise


# ---------------------------------------------------------------------------
# MCP tool adapters + server
# ---------------------------------------------------------------------------

@tool(
    "get_calendar",
    "List upcoming appointments for a care recipient within a horizon.",
    {"care_recipient_id": str, "horizon_days": int},
)
async def _get_calendar_tool(args: dict) -> dict:
    """MCP adapter for :func:`get_calendar`.

    Args:
        args: MCP arguments dict; requires ``care_recipient_id`` and optional
            ``horizon_days`` (defaults to 30).

    Returns:
        MCP content-block envelope wrapping the list of Appointment dicts.
    """
    return _mcp_result(
        get_calendar(args["care_recipient_id"], args.get("horizon_days", 30))
    )


@tool(
    "schedule_appointment",
    "Schedule and confirm a new appointment with a provider.",
    {
        "provider_id": str,
        "care_recipient_id": str,
        "preferred_datetime": str,
    },
)
async def _schedule_appointment_tool(args: dict) -> dict:
    """MCP adapter for :func:`schedule_appointment`.

    Args:
        args: MCP arguments dict; requires ``provider_id``,
            ``care_recipient_id``, ``preferred_datetime``.

    Returns:
        MCP content-block envelope wrapping the confirmation dict.
    """
    return _mcp_result(
        schedule_appointment(
            args["provider_id"],
            args["care_recipient_id"],
            args["preferred_datetime"],
        )
    )


calendar_server = create_sdk_mcp_server(
    name="calendar",
    version="1.0.0",
    tools=[_get_calendar_tool, _schedule_appointment_tool],
)
