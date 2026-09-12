"""Appointment tools for CareBridge.

Simulates external calendar API calls using fixture data.
All tools follow the audit-first pattern: write a pending audit event
BEFORE executing, then update with the final outcome.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from src.models.schemas import Appointment, ChecklistResult
from src.models.audit_log import write_audit_event
from src.models.escalation_logic import classify_action
from src.tools.retry import with_retry

logger = logging.getLogger(__name__)

FIXTURES_PATH = Path(__file__).parent.parent.parent / "fixtures"


def _load_appointments() -> list[dict]:
    """Load appointment fixtures.

    Returns:
        List of raw appointment dictionaries from the JSON fixture file.

    Raises:
        FileNotFoundError: If the fixtures file does not exist.
        json.JSONDecodeError: If the fixtures file contains invalid JSON.
    """
    with open(FIXTURES_PATH / "appointments.json") as f:
        return json.load(f)


def get_calendar(care_recipient_id: str, horizon_days: int = 30) -> list[Appointment]:
    """Get upcoming appointments for a care recipient.

    Loads appointment fixtures, filters by care_recipient_id, and returns
    only those within the specified horizon from now.

    Args:
        care_recipient_id: The care recipient identifier.
        horizon_days: Number of days to look ahead (default 30).

    Returns:
        List of Appointment objects within the horizon.

    Raises:
        ValueError: If care_recipient_id not found in any fixture record.
    """
    raw_appointments = _load_appointments()

    # Filter by care_recipient_id
    recipient_appts = [
        a for a in raw_appointments if a["care_recipient_id"] == care_recipient_id
    ]

    if not recipient_appts:
        raise ValueError(
            f"No appointments found for care_recipient_id: {care_recipient_id}"
        )

    now = datetime.now(timezone.utc)
    horizon_end = now + timedelta(days=horizon_days)

    results: list[Appointment] = []
    for appt in recipient_appts:
        appt_dt = datetime.fromisoformat(appt["datetime"].replace("Z", "+00:00"))
        if now <= appt_dt <= horizon_end:
            results.append(Appointment(**appt))

    logger.info(
        "get_calendar: found %d appointments for %s within %d days",
        len(results), care_recipient_id, horizon_days,
    )
    return results


async def _simulate_calendar_api(
    provider_id: str,
    care_recipient_id: str,
    preferred_datetime: datetime,
) -> Appointment:
    """Simulate an external calendar API call to schedule an appointment.

    This is a mock implementation that creates an Appointment in-memory.
    On Day 2 this will be replaced with a real MCP server call.

    Args:
        provider_id: The healthcare provider identifier.
        care_recipient_id: The care recipient identifier.
        preferred_datetime: Requested appointment datetime.

    Returns:
        The newly scheduled Appointment.
    """
    logger.info(
        "Simulating calendar API call: provider=%s, recipient=%s, datetime=%s",
        provider_id, care_recipient_id, preferred_datetime.isoformat(),
    )
    return Appointment(
        appointment_id=str(uuid4()),
        provider_name=f"Provider-{provider_id}",
        specialty="General",
        datetime=preferred_datetime,
        location="TBD",
        prep_required=[],
        transportation_needed=False,
        care_recipient_id=care_recipient_id,
    )


async def schedule_appointment(
    provider_id: str,
    care_recipient_id: str,
    preferred_datetime: datetime,
) -> Appointment:
    """Schedule a new appointment with a provider.

    Writes an audit event with outcome="pending" BEFORE executing,
    then writes a follow-up audit event with the final outcome.
    Uses with_retry() for the simulated calendar API call.

    Args:
        provider_id: The healthcare provider identifier.
        care_recipient_id: The care recipient identifier.
        preferred_datetime: Requested appointment datetime.

    Returns:
        The scheduled Appointment.

    Raises:
        RuntimeError: If the calendar API call fails after retries.
    """
    action_type = "schedule_appointment"
    classification = classify_action(action_type)
    correlation_id = str(uuid4())

    # Audit: BEFORE action with outcome="pending"
    write_audit_event(
        actor="appointment",
        action_type=action_type,
        care_recipient_id=care_recipient_id,
        rationale=(
            f"Scheduling appointment with provider {provider_id} "
            f"at {preferred_datetime.isoformat()}"
        ),
        outcome="pending",
        correlation_id=correlation_id,
    )

    try:
        appointment: Appointment = await with_retry(
            _simulate_calendar_api,
            provider_id,
            care_recipient_id,
            preferred_datetime,
        )

        # Audit: AFTER action with outcome="success"
        write_audit_event(
            actor="appointment",
            action_type=action_type,
            care_recipient_id=care_recipient_id,
            rationale=(
                f"Successfully scheduled appointment {appointment.appointment_id} "
                f"with provider {provider_id}"
            ),
            outcome="success",
            correlation_id=correlation_id,
        )

        logger.info(
            "schedule_appointment: created %s for recipient %s (classification=%s)",
            appointment.appointment_id, care_recipient_id, classification,
        )
        return appointment

    except Exception as exc:
        # Audit: AFTER action with outcome="failure"
        write_audit_event(
            actor="appointment",
            action_type=action_type,
            care_recipient_id=care_recipient_id,
            rationale=f"Failed to schedule appointment with provider {provider_id}: {exc}",
            outcome="failure",
            correlation_id=correlation_id,
        )

        logger.error(
            "schedule_appointment failed for recipient %s: %s",
            care_recipient_id, exc,
        )
        raise RuntimeError(
            f"Calendar API call failed after retries: {exc}"
        ) from exc


def send_prep_checklist(appointment_id: str) -> ChecklistResult:
    """Send preparation checklist for an upcoming appointment.

    Looks up the appointment in fixtures and returns a ChecklistResult
    indicating the checklist was delivered.

    Args:
        appointment_id: The appointment to send checklist for.

    Returns:
        ChecklistResult with delivery status.

    Raises:
        ValueError: If appointment_id not found in fixtures.
    """
    raw_appointments = _load_appointments()

    match: Optional[dict] = None
    for appt in raw_appointments:
        if appt["appointment_id"] == appointment_id:
            match = appt
            break

    if match is None:
        raise ValueError(
            f"Appointment not found: {appointment_id}"
        )

    logger.info(
        "send_prep_checklist: sent checklist for appointment %s (prep: %s)",
        appointment_id, match.get("prep_required", []),
    )

    return ChecklistResult(
        appointment_id=appointment_id,
        checklist_sent=True,
        delivery_status="sent",
        sent_at=datetime.now(timezone.utc),
    )
