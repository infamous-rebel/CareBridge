---
kind: external_dependency
name: Strands Agents SDK — agents-as-tools orchestration framework
slug: strands-agents-sdk
category: external_dependency
category_hints:
    - framework_behavior
    - sdk_real_api
scope:
    - '**'
---


- Integration point: `src/agents/supervisor_agent.py` imports `from strands import Agent` and registers all four specialist agents as callable tools.
- Graceful degradation: when credentials are absent, the Supervisor falls back to direct tool routing without an LLM call so `python main.py` still runs.