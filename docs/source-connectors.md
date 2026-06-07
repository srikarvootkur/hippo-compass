# Source Connectors

Recommended order:

1. Google Health API for Fitbit-backed activity/fitness data.
2. Google Calendar and Tasks.
3. Cronometer export/API.
4. Hevy.
5. RingConn.
6. Telegram approval interface.
7. Finance aggregators in read-only mode.
8. Mac iMessage bridge.

Each connector should write to `source_records` first, then create normalized facts and memory candidates.

Never let connector code perform sensitive external actions without creating an approval.

## Connector Shape

Each connector should follow the same simple path:

1. Pull or receive source data.
2. Store the raw payload in `source_records`.
3. Normalize the important fields into `normalized_payload`.
4. Generate memory candidates only for durable facts or patterns.
5. Queue recommendations or sensitive actions through approvals.

This keeps connectors boring and makes the assistant easier to debug later.

Use LangGraph for connectors that need durable state, retries, or approval checkpoints. Keep simple one-shot imports as boring worker/API code.

## Google Health API

The first health connector is Google Health API with the readonly activity/fitness scope:

```text
https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly
```

See `docs/google-health-connector.md`.
