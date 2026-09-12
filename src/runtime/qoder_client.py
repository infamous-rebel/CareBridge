"""Qoder runtime client factory for CareBridge.

Builds a ``QoderSDKClient`` with all four CareBridge MCP servers attached via
``QoderAgentOptions``. This is the runnable qoder-runtime counterpart to the
Strands-based ``create_supervisor_agent`` path.

Why this module exists
----------------------
The MCP server configs produced by ``qoder_agent_sdk.create_sdk_mcp_server``
(shape ``{"type": "sdk", "name": ..., "instance": <mcp Server>}``) are consumed
by ``QoderAgentOptions.mcp_servers`` — a ``dict[str, McpServerConfig]`` keyed by
server name — which is exactly what ``src.mcp.get_mcp_server_configs()`` returns.
There is no ``Agent(mcp_servers=[...])`` constructor in either SDK, so the client
+ options object is the correct attachment point.

The client is built **lazily** (never at import time) and cached behind a
thread-safe singleton via :func:`get_qoder_client`.
"""

import logging
import threading
from typing import TYPE_CHECKING, Any, Optional

from src.mcp import get_mcp_server_configs

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from qoder_agent_sdk import QoderSDKClient

logger = logging.getLogger(__name__)

# Cached singleton + its guard. Instantiation is lazy (see get_qoder_client).
_client: Optional["QoderSDKClient"] = None
_client_lock = threading.Lock()


def create_qoder_client() -> Any:
    """Build a ``QoderSDKClient`` with all four CareBridge MCP servers attached.

    Wires the in-process MCP registry (pharmacy, messaging, delivery, calendar)
    into ``QoderAgentOptions.mcp_servers`` and returns a configured client. The
    client is only constructed here — it is not connected or started (that is the
    caller's responsibility via the client's async context manager).

    Returns:
        A configured ``qoder_agent_sdk.QoderSDKClient`` instance.

    Raises:
        RuntimeError: If ``qoder_agent_sdk`` is not installed.
    """
    try:
        from qoder_agent_sdk import QoderAgentOptions, QoderSDKClient
    except ImportError as exc:
        raise RuntimeError(
            "qoder_agent_sdk is not installed; cannot build the Qoder runtime "
            "client. Install it with `pip install qoder-agent-sdk>=1.0.0`."
        ) from exc

    # Name-keyed dict of McpSdkServerConfig — the exact shape QoderAgentOptions
    # expects for mcp_servers.
    mcp_servers = get_mcp_server_configs()
    options = QoderAgentOptions(mcp_servers=mcp_servers)
    client = QoderSDKClient(options=options)

    logger.info(
        "Qoder runtime client created with MCP servers: %s",
        ", ".join(sorted(mcp_servers)),
    )
    return client


def get_qoder_client() -> Any:
    """Return a cached, thread-safe singleton ``QoderSDKClient``.

    Lazily builds the client on first call (double-checked locking) and caches
    it for subsequent calls. Never instantiates at import time.

    Returns:
        The shared ``qoder_agent_sdk.QoderSDKClient`` instance.

    Raises:
        RuntimeError: If ``qoder_agent_sdk`` is not installed.
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = create_qoder_client()
    return _client


def reset_qoder_client() -> None:
    """Clear the cached singleton. Thread-safe; primarily used by tests."""
    global _client
    with _client_lock:
        _client = None
