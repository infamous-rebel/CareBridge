"""MCP registry introspection.

``GET /mcp/servers`` lists the in-process MCP servers from
``src.mcp.get_mcp_server_configs()`` with their transport type and tool names.
Tool names are read by invoking each low-level ``mcp`` server's ``ListTools``
handler; if a server cannot be introspected the tool list degrades to empty
(logged, never silently swallowed). Read-only → 200 regardless of LLM runtime.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends

from src.api.dependencies import get_current_user
from src.api.schemas import MCPServerInfo, MCPServersResponse
from src.mcp import get_mcp_server_configs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])


async def _list_tool_names(instance: Any) -> list[str]:
    """Best-effort synchronous-name extraction from a low-level MCP server.

    Args:
        instance: The ``mcp.server.lowlevel.Server`` from a server config.

    Returns:
        Tool names advertised by the server, or [] if introspection fails.
    """
    try:
        import mcp.types as mt

        handlers = getattr(instance, "request_handlers", None)
        if not handlers:
            return []
        handler = handlers.get(mt.ListToolsRequest)
        if handler is None:
            return []
        result = await handler(mt.ListToolsRequest(method="tools/list"))
        root = getattr(result, "root", result)
        tools = getattr(root, "tools", None) or []
        return [t.name for t in tools if getattr(t, "name", None)]
    except Exception as exc:
        logger.warning(
            "MCP tool introspection failed for a server: %s", type(exc).__name__
        )
        return []


@router.get("/servers", response_model=MCPServersResponse)
async def list_mcp_servers(
    _user: dict = Depends(get_current_user),
) -> MCPServersResponse:
    """Return the registered MCP servers and their tools.

    Args:
        _user: Injected authenticated user.

    Returns:
        ``MCPServersResponse`` with a count and one ``MCPServerInfo`` per server.
    """
    configs = get_mcp_server_configs()
    servers: list[MCPServerInfo] = []
    for name in sorted(configs):
        cfg = configs[name]
        instance = cfg.get("instance")
        tools = await _list_tool_names(instance)
        servers.append(
            MCPServerInfo(
                name=cfg.get("name", name),
                type=str(cfg.get("type", "unknown")),
                tools=tools,
            )
        )
    logger.info("MCP introspection returned %d server(s)", len(servers))
    return MCPServersResponse(count=len(servers), servers=servers)
