"""CareBridge Communication Tools — messaging and notification utilities.

Simulates external messaging APIs (SMS, email, phone) by logging to the
logs/ directory. Real MCP-based integrations are Day 2.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from src.models.schemas import (
    AlertResult,
    AuditEvent,
    FamilyMember,
    FamilyPreferences,
    PendingAction,
    StatusSummary,
)
from src.models.audit_log import write_audit_event, get_audit_events
from src.models.escalation_logic import classify_action
from src.tools.retry import with_retry

logger = logging.getLogger(__name__)

FIXTURES_PATH = Path(__file__).parent.parent.parent / "fixtures"
LOGS_PATH = Path(__file__).parent.parent.parent / "logs"


def _load_family_members() -> list[dict]:
    """Load family member fixtures.

    Returns:
        List of family member dicts from the JSON fixture file.
    """
    with open(FIXTURES_PATH / "family_members.json") as f:
        return json.load(f)


def _log_message(record: dict) -> None:
    """Append a JSON-lines message record to logs/messages.log.

    Args:
        record: The message record to persist.
    """
    LOGS_PATH.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_PATH / "messages.log"
    with open(log_file, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


async def send_alert(
    recipient_id: str,
    message: str,
    level: Literal["info", "alert", "emergency"],
) -> AlertResult:
    """Send an alert to a care recipient's family.

    Behavior by level:
    - "emergency": SMS + email + phone call to ALL family members in escalation_order
    - "alert": SMS to primary caregiver, email to others
    - "info": Batch into daily digest

    Args:
        recipient_id: The care recipient whose family should be notified.
        message: The alert message content.
        level: Alert severity level.

    Returns:
        AlertResult with delivery status and channel used.

    Raises:
        RuntimeError: If messaging API fails after retries.
    """
    correlation_id = str(uuid4())

    # Write "before action" audit event
    write_audit_event(
        actor="communication",
        action_type="send_alert",
        care_recipient_id=recipient_id,
        rationale=f"Sending {level}-level alert: {message}",
        outcome="pending",
        correlation_id=correlation_id,
    )

    try:
        family_members = _load_family_members()

        # Determine channels and recipients based on level
        if level == "emergency":
            channel_used = "sms,email,phone"
            targets = [m["name"] for m in family_members]
        elif level == "alert":
            channel_used = "sms,email"
            targets = []
            for member in family_members:
                if member.get("escalation_priority") == 1:
                    targets.append(f"{member['name']} (SMS)")
                else:
                    targets.append(f"{member['name']} (email)")
        else:
            # info — batch into daily digest
            channel_used = "digest"
            targets = ["daily_digest_queue"]

        # Simulate sending by logging each target
        for target in targets:
            _log_message({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "recipient_id": recipient_id,
                "target": target,
                "channel": channel_used,
                "level": level,
                "message": message,
            })

        logger.info(
            f"Alert sent to {len(targets)} target(s) via {channel_used} "
            f"for recipient {recipient_id}"
        )

        # Write follow-up success audit event
        write_audit_event(
            actor="communication",
            action_type="send_alert",
            care_recipient_id=recipient_id,
            rationale=f"Successfully sent {level}-level alert to {len(targets)} target(s)",
            outcome="success",
            correlation_id=correlation_id,
        )

        return AlertResult(
            alert_id=str(uuid4()),
            delivery_status="sent",
            channel_used=channel_used,
            sent_at=datetime.now(timezone.utc),
        )

    except Exception as e:
        logger.error(f"Failed to send alert for {recipient_id}: {e}")

        # Write failure audit event
        write_audit_event(
            actor="communication",
            action_type="send_alert",
            care_recipient_id=recipient_id,
            rationale=f"Failed to send {level}-level alert: {e}",
            outcome="failure",
            correlation_id=correlation_id,
        )

        raise RuntimeError(
            f"Messaging API failed for recipient {recipient_id}: {e}"
        ) from e


def synthesize_status(care_recipient_id: str) -> StatusSummary:
    """Synthesize current care status for a care recipient.

    Queries the audit trail for recent events and pending actions, then
    builds a human-readable summary.

    Args:
        care_recipient_id: The care recipient identifier.

    Returns:
        StatusSummary with summary text, recent events, and pending actions.
    """
    events = get_audit_events(care_recipient_id=care_recipient_id)

    # Build recent audit events as Pydantic models
    recent_events: list[AuditEvent] = []
    pending_actions: list[PendingAction] = []

    for evt in events:
        try:
            audit_event = AuditEvent(
                event_id=evt["event_id"],
                timestamp=evt["timestamp"],
                actor=evt["actor"],
                action_type=evt["action_type"],
                care_recipient_id=evt["care_recipient_id"],
                rationale=evt["rationale"],
                outcome=evt["outcome"],
                correlation_id=evt["correlation_id"],
                authorization_ref=evt.get("authorization_ref"),
            )
            recent_events.append(audit_event)

            if evt["outcome"] == "pending":
                pending_actions.append(
                    PendingAction(
                        action_id=evt["event_id"],
                        action_type=evt["action_type"],
                        care_recipient_id=evt["care_recipient_id"],
                        rationale=evt["rationale"],
                        requested_at=evt["timestamp"],
                        status="pending",
                        authorization_ref=evt.get("authorization_ref"),
                    )
                )
        except (KeyError, ValueError) as e:
            logger.warning(f"Skipping malformed audit event: {e}")

    # Build summary text from recent activity
    if recent_events:
        last_event = recent_events[0]
        summary_text = (
            f"Care recipient {care_recipient_id}: "
            f"{len(recent_events)} recent event(s). "
            f"Last action: {last_event.action_type} "
            f"({last_event.outcome}) at {last_event.timestamp}."
        )
        if pending_actions:
            summary_text += (
                f" {len(pending_actions)} pending action(s) awaiting resolution."
            )
    else:
        summary_text = (
            f"Care recipient {care_recipient_id}: No recent events recorded."
        )

    return StatusSummary(
        care_recipient_id=care_recipient_id,
        summary_text=summary_text,
        recent_events=recent_events,
        pending_actions=pending_actions,
    )


def get_family_preferences(family_id: str) -> FamilyPreferences:
    """Get family notification preferences and escalation order.

    Loads family member data from fixtures, filters by family_id, and
    builds an escalation order sorted by priority.

    Args:
        family_id: The family identifier.

    Returns:
        FamilyPreferences with members and escalation order.

    Raises:
        ValueError: If family_id not found in fixtures.
    """
    all_members = _load_family_members()
    matching = [m for m in all_members if m["family_id"] == family_id]

    if not matching:
        raise ValueError(f"Family ID '{family_id}' not found in fixtures")

    # Build FamilyMember models
    members = [
        FamilyMember(
            family_id=m["family_id"],
            name=m["name"],
            relationship=m["relationship"],
            phone=m.get("phone"),
            email=m.get("email"),
            notification_preference=m.get("notification_preference", "both"),
            escalation_priority=m.get("escalation_priority", 99),
        )
        for m in matching
    ]

    # Escalation order: sorted by priority ascending
    escalation_order = [
        m.name for m in sorted(members, key=lambda m: m.escalation_priority)
    ]

    return FamilyPreferences(
        family_id=family_id,
        members=members,
        escalation_order=escalation_order,
    )
