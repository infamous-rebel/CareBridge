"""CareBridge REST API package.

Production-grade FastAPI backend that the React caregiver dashboard calls.
Exposes authenticated, rate-limited, audit-backed endpoints over the existing
Supervisor Agent, the immutable SQLite audit trail, and the in-process MCP
registry.

Public entrypoints:
    - ``src.api.main.app``          — the ASGI application (uvicorn target).
    - ``src.api.main.create_app``   — application factory.
    - ``src.api.config.get_settings`` — cached runtime configuration.
"""

from src.api.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
