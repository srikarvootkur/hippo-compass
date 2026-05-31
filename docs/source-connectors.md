# Source Connectors

Recommended order:

1. Google Calendar and Tasks.
2. Cronometer export/API.
3. Hevy.
4. RingConn.
5. Telegram approval interface.
6. Finance aggregators in read-only mode.
7. Mac iMessage bridge.

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
