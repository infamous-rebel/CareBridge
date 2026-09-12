"""CareBridge MCP integration layer — in-process Model Context Protocol servers.

This package exposes the four MCP servers that sit between the specialized
agents and the (mocked) external world — see architecture.md §5 and SPEC.md §6:

=================  =========================================================
Server             Tools
=================  =========================================================
``pharmacy``       check_refill_status, order_refill, get_medication_schedule
``messaging``      send_sms, send_email
``delivery``       check_delivery_status, order_grocery, order_pharmacy_delivery
``calendar``       get_calendar, schedule_appointment
=================  =========================================================

Transport
---------
Pharmacy, Messaging, and Delivery run **in-process** (ADR-002): zero subprocess
overhead and direct access to shared Python state (the immutable audit trail and
the JSON fixtures). Calendar is specified as an external SSE connector
(SPEC.md §6.4); the in-process mock in ``calendar_server.py`` is the spec's
documented fallback and a Day-2 swap to SSE, keeping the same tool contract.

All four servers are built with the Qoder Agent SDK's in-process MCP helpers
``qoder_agent_sdk.tool`` (a decorator producing an ``SdkMcpTool``) and
``qoder_agent_sdk.create_sdk_mcp_server`` (returning an ``McpSdkServerConfig``
of shape ``{"type": "sdk", "name": <name>, "instance": <mcp Server>}``). That
config is what an agent runtime consumes via ``mcp_servers``.

Registry
--------
``MCP_SERVERS`` maps each server name to its config. ``get_server(name)`` fetches
one by name and ``get_mcp_server_configs()`` returns all of them keyed by name,
so a runtime can wire the whole layer — or pull a single server by name without
shadowing the submodule of the same name — without importing each module
individually.

Note on tool signatures: the Qoder SDK requires MCP tool handlers to be
``async def handler(args: dict) -> dict`` with a separate ``input_schema``. To
preserve the typed SPEC signatures (e.g. ``check_refill_status(medication_id:
str) -> dict``), each server module implements the tool as a typed business
function and registers a thin ``@tool`` adapter that unpacks ``args`` and wraps
the result in the MCP content-block envelope.
"""

from src.mcp.pharmacy_server import pharmacy_server
from src.mcp.messaging_server import messaging_server
from src.mcp.delivery_server import delivery_server
from src.mcp.calendar_server import calendar_server

# Registry of the in-process MCP servers, keyed by server name. Each value is an
# McpSdkServerConfig ({"type": "sdk", "name": ..., "instance": ...}) returned by
# qoder_agent_sdk.create_sdk_mcp_server, ready to pass to a runtime's
# mcp_servers configuration.
MCP_SERVERS: dict[str, dict] = {
    "pharmacy": pharmacy_server,
    "messaging": messaging_server,
    "delivery": delivery_server,
    "calendar": calendar_server,
}


def get_server(name: str) -> dict:
    """Return the in-process MCP server config registered under ``name``.

    Args:
        name: One of "pharmacy", "messaging", "delivery", "calendar".

    Returns:
        The McpSdkServerConfig dict for that server.

    Raises:
        KeyError: If no server is registered under ``name``.
    """
    if name not in MCP_SERVERS:
        raise KeyError(
            f"Unknown MCP server: {name}. Registered: {sorted(MCP_SERVERS)}"
        )
    return MCP_SERVERS[name]


def get_mcp_server_configs() -> dict[str, dict]:
    """Return all in-process MCP server configs, keyed by server name.

    Keying by name lets an agent pull a single server — e.g.
    ``get_mcp_server_configs()["pharmacy"]`` — without importing the
    ``pharmacy_server`` symbol (which shadows the submodule of the same name).
    This dict-keyed shape also matches the installed ``qoder_agent_sdk``
    contract, where ``QoderAgentOptions.mcp_servers`` is a
    ``dict[str, McpServerConfig]``.

    Returns:
        Dict mapping server name to its McpSdkServerConfig:
        ``{"pharmacy": ..., "messaging": ..., "delivery": ..., "calendar": ...}``.
    """
    return dict(MCP_SERVERS)


__all__ = [
    "pharmacy_server",
    "messaging_server",
    "delivery_server",
    "calendar_server",
    "MCP_SERVERS",
    "get_server",
    "get_mcp_server_configs",
]
