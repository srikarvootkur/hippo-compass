# OpenAI Agents SDK Workflows

Use the OpenAI Agents SDK for focused specialist agents that need OpenAI-native tools, guardrails, handoffs, tracing, or structured model calls.

LangGraph is the default durable workflow orchestrator. OpenAI Agents SDK services should usually sit behind LangGraph, not replace it.

Initial workflows:

- Cronometer daily review
- Weekly health review
- Writing-style reply draft
- Journal/coaching synthesis
- City/date planning

The first implemented specialist endpoint is:

```text
POST /workflows/cronometer/daily-review
```

Mock mode works without an OpenAI API key. Real agent mode uses `OPENAI_API_KEY` and `OPENAI_MODEL`.

The SDK should not be treated as durable memory. Persist durable facts and recommendations through `assistant-api` into Postgres.
