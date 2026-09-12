---
kind: external_dependency
name: Twilio and SendGrid — SMS/email/call delivery channels for the Communication Agent
slug: twilio-sendgrid
category: external_dependency
category_hints:
    - vendor_identity
    - auth_protocol
scope:
    - '**'
---

The Communication Agent delivers alerts through Twilio (SMS + phone calls) and SendGrid (email), configured via environment variables: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `SENDGRID_API_KEY`. These are consumed by the Messaging MCP server.

- Channel selection: `level="emergency"` triggers SMS + email + phone call to all family members in escalation order; `level="alert"` sends SMS to primary caregiver and email to others; `level="info"` batches into a daily digest.
- Secret injection: credentials live only in `.env`; never committed to the repo.
- Current state: during the hackathon build these channels are mocked/logged to `logs/messages.log`; production wiring replaces the mock with real Twilio/SendGrid clients.
- Verify current Twilio Account SID format and SendGrid API key scope against each vendor's docs before enabling.