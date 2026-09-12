"""CareBridge Messaging MCP server — in-process mock of SMS/email delivery.

Runs in-process via the Qoder Agent SDK's ``create_sdk_mcp_server`` / ``@tool``
helpers (architecture.md §5, ADR-002). Backs the Communication Agent with two
tools (SPEC.md §6.2):

* ``send_sms(recipient_id, message, level)`` — deliver an SMS
* ``send_email(recipient_id, message, level)`` — deliver an email

Mock behaviour: every message is appended to ``logs/messages.log`` with an ISO
timestamp, and the tool returns a synthetic delivery receipt. ``level`` must be
one of ``{"info", "alert", "emergency"}``; invalid levels are rejected. Every
tool call writes exactly one audit event (actor="communication").

As in ``pharmacy_server``, each tool is a typed business function (the SPEC
contract, directly callable/testable) plus a thin ``@tool`` async adapter that
bridges the Qoder SDK's ``async def handler(args: dict) -> dict`` convention.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from qoder_agent_sdk import create_sdk_mcp_server, tool

from src.models.audit_log import write_audit_event

logger = logging.getLogger(__name__)

LOGS_PATH = Path(__file__).parent.parent.parent / "logs"

# Audit actor for every tool on this server (AGENTS.md §7).
_ACTOR = "communication"

# Accepted escalation levels (AGENTS.md §8).
VALID_LEVELS = frozenset({"info", "alert", "emergency"})

Level = Literal["info", "alert", "emergency"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _audit(
    action_type: str,
    care_recipient_id: str,
    rationale: str,
    outcome: str,
    correlation_id: str,
) -> None:
    """Write one messaging audit event (actor="communication").

    Args:
        action_type: The MCP tool name ("send_sms" or "send_email").
        care_recipient_id: FK to the care recipient (the recipient_id).
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


def _append_message_log(record: dict) -> None:
    """Append a JSON-lines message record to ``logs/messages.log``.

    Args:
        record: The message record to persist.
    """
    LOGS_PATH.mkdir(parents=True, exist_ok=True)
    with open(LOGS_PATH / "messages.log", "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _mcp_result(payload: object) -> dict:
    """Wrap a tool payload in the MCP content-block envelope.

    Args:
        payload: JSON-serialisable tool result.

    Returns:
        ``{"content": [{"type": "text", "text": <json>}]}``.
    """
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


def _dispatch(
    action_type: str,
    channel: str,
    recipient_id: str,
    message: str,
    level: str,
) -> dict:
    """Validate, log, and audit a single message delivery.

    Shared implementation for :func:`send_sms` and :func:`send_email`; the only
    difference between them is the ``channel``/``action_type``.

    Args:
        action_type: The MCP tool name (used as the audit action_type).
        channel: Delivery channel, "sms" or "email".
        recipient_id: The care recipient / family member identifier.
        message: The message body.
        level: Escalation level; must be one of ``VALID_LEVELS``.

    Returns:
        Dict ``{"status": "delivered", "channel": channel, "sent_at": <ISO>}``.

    Raises:
        ValueError: If ``level`` is not one of info/alert/emergency.
        OSError: If the message log cannot be written.
    """
    correlation_id = str(uuid4())

    if level not in VALID_LEVELS:
        # Validation failure: audit it (never silently fail) then raise.
        _audit(
            action_type,
            recipient_id,
            f"Rejected {channel} message to {recipient_id}: invalid level '{level}'",
            "failure",
            correlation_id,
        )
        raise ValueError(
            f"Invalid level '{level}': must be one of "
            f"{sorted(VALID_LEVELS)}"
        )

    try:
        sent_at = datetime.now(timezone.utc)
        _append_message_log({
            "timestamp": sent_at.isoformat(),
            "recipient_id": recipient_id,
            "channel": channel,
            "level": level,
            "message": message,
        })

        _audit(
            action_type,
            recipient_id,
            f"Sent {level}-level {channel} message to {recipient_id}",
            "success",
            correlation_id,
        )
        logger.info(
            "%s: delivered %s-level message to %s", action_type, level, recipient_id
        )
        return {
            "status": "delivered",
            "channel": channel,
            "sent_at": sent_at.isoformat(),
        }
    except Exception as e:
        _audit(
            action_type,
            recipient_id,
            f"Failed to send {level}-level {channel} message to {recipient_id}: {e}",
            "failure",
            correlation_id,
        )
        logger.error("%s failed for %s: %s", action_type, recipient_id, e)
        raise


# ---------------------------------------------------------------------------
# Tool business logic (spec signatures)
# ---------------------------------------------------------------------------

def send_sms(recipient_id: str, message: str, level: Level) -> dict:
    """Send an SMS to a recipient.

    Args:
        recipient_id: The care recipient / family member identifier.
        message: The SMS body.
        level: Escalation level; one of "info", "alert", "emergency".

    Returns:
        Dict ``{"status": "delivered", "channel": "sms", "sent_at": <ISO>}``.

    Raises:
        ValueError: If ``level`` is invalid.
        OSError: If the message log cannot be written.
    """
    return _dispatch("send_sms", "sms", recipient_id, message, level)


def send_email(recipient_id: str, message: str, level: Level) -> dict:
    """Send an email to a recipient.

    Args:
        recipient_id: The care recipient / family member identifier.
        message: The email body.
        level: Escalation level; one of "info", "alert", "emergency".

    Returns:
        Dict ``{"status": "delivered", "channel": "email", "sent_at": <ISO>}``.

    Raises:
        ValueError: If ``level`` is invalid.
        OSError: If the message log cannot be written.
    """
    return _dispatch("send_email", "email", recipient_id, message, level)


# ---------------------------------------------------------------------------
# MCP tool adapters + server
# ---------------------------------------------------------------------------

@tool(
    "send_sms",
    "Send an SMS alert to a recipient at info/alert/emergency level.",
    {"recipient_id": str, "message": str, "level": str},
)
async def _send_sms_tool(args: dict) -> dict:
    """MCP adapter for :func:`send_sms`.

    Args:
        args: MCP arguments dict; requires ``recipient_id``, ``message``, ``level``.

    Returns:
        MCP content-block envelope wrapping the delivery receipt.
    """
    return _mcp_result(
        send_sms(args["recipient_id"], args["message"], args["level"])
    )


@tool(
    "send_email",
    "Send an email alert to a recipient at info/alert/emergency level.",
    {"recipient_id": str, "message": str, "level": str},
)
async def _send_email_tool(args: dict) -> dict:
    """MCP adapter for :func:`send_email`.

    Args:
        args: MCP arguments dict; requires ``recipient_id``, ``message``, ``level``.

    Returns:
        MCP content-block envelope wrapping the delivery receipt.
    """
    return _mcp_result(
        send_email(args["recipient_id"], args["message"], args["level"])
    )


messaging_server = create_sdk_mcp_server(
    name="messaging",
    version="1.0.0",
    tools=[_send_sms_tool, _send_email_tool],
)
