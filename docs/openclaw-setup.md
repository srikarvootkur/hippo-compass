# OpenClaw Setup

OpenClaw is the first agent shell. Configure it to call `assistant-api` endpoints as tools.

Minimum tool endpoints:

- `POST /memory/search`
- `POST /memory/write`
- `POST /journal_entries`
- `GET /recommendations`
- `POST /recommendations`
- `POST /approvals`
- `POST /tool_runs`
- `POST /workflows/cronometer/daily-review`

OpenClaw should authenticate with `X-Assistant-API-Key`.

Do not put durable memory or integration secrets directly inside OpenClaw configuration when those can live behind `assistant-api`.

OpenClaw should call `assistant-api`, not `langgraph-workflows` or `agents-workflows` directly. That keeps the workflow internals replaceable.

## Workspace Skills

This repo includes starter OpenClaw-style workspace skills:

- `skills/search-memory`
- `skills/save-journal-entry`
- `skills/review-recommendations`

Configure their environment with:

```text
HIPPO_COMPASS_API_URL=https://assistant.yourdomain.com
HIPPO_COMPASS_API_KEY=your-secret
```

## Why This Boundary Exists

OpenClaw is the first shell, not the permanent source of truth.

If another agent framework replaces OpenClaw later, it should call the same `assistant-api` endpoints and use the same Postgres memory. That is the whole portability bet.
