---
kind: external_dependency
name: Amazon Bedrock — Claude Sonnet model hosting for the Supervisor Agent
slug: amazon-bedrock
category: external_dependency
category_hints:
    - vendor_identity
    - auth_protocol
scope:
    - '**'
---

The Supervisor Agent's LLM layer targets Amazon Bedrock, specifically the `anthropic.claude-sonnet-4` model (model id configured via `BEDROCK_MODEL_ID`). Authentication is via standard AWS credential environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) and region (`AWS_REGION=us-east-1`).

- Role: hosts the Claude model that powers the Supervisor's intent classification and delegation decisions.
- Secret injection: all credentials come from `.env` (loaded via `python-dotenv`); no keys are hardcoded.
- Current state: development runs without Bedrock credentials by falling back to direct tool dispatch; production deployment on Qoder Cloud Agents expects a live Bedrock endpoint.
- Verify exact model id and availability against the latest Bedrock model registry before enabling.