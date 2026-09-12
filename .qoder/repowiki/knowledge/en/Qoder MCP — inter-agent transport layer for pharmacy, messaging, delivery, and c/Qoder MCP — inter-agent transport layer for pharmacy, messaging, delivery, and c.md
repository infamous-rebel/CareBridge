---
kind: external_dependency
name: Qoder MCP — inter-agent transport layer for pharmacy, messaging, delivery, and calendar services
slug: qoder-mcp
category: external_dependency
category_hints:
    - framework_behavior
    - client_constraint
scope:
    - '**'
---

CareBridge integrates external systems (pharmacy, messaging, delivery, calendar) through Qoder's Model Context Protocol (MCP). Three servers run **in-process** via the Qoder SDK (`create_sdk_mcp_server`) — Pharmacy, Messaging, Delivery — while Calendar connects externally via SSE using the Qoder Connector.

- Transport shape: in-process SDK for custom tools that need shared Python state (audit log, fixtures); SSE for Calendar because Qoder already provides a connector.
- Configuration: server endpoints and API keys are read from `.env` (`PHARMACY_MCP_URL`, `CALENDAR_MCP_URL`, `DELIVERY_MCP_URL`, `MESSAGING_MCP_URL`, plus per-service `*_API_KEY`).
- Fallback behavior: if a connector or server is unavailable, the system logs to audit and notifies the caregiver rather than failing silently.
- Production target: Qoder Cloud Agents with identity isolation per family; dev uses local HTTP endpoints pointing at mock servers.