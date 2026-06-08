# LangGraph Workflows

LangGraph is the long-term workflow engine for Hippo Compass.

Use it for flows that need:

- durable state
- human-in-the-loop approval
- pause/resume
- retries
- long-running background jobs
- clear workflow state
- model/provider flexibility

## Current Service

The service lives in:

```text
services/langgraph-workflows
```

It exposes:

```text
GET /health
POST /workflows/cronometer/daily-review
POST /workflows/google-health/coach-review
```

The Cronometer workflow currently calls the OpenAI Agents SDK specialist service, then wraps the result as a durable workflow output with recommendation and memory candidates.

The Google Health coach workflow attaches a curated evidence pack, calls the specialist service, and returns wellness coaching with citations, safety level, recommendation, and memory candidates.

## Design Rule

Use LangGraph for orchestration. Use specialist agent frameworks behind it when useful.

```text
assistant-api
  -> langgraph-workflows
  -> specialist service or connector
  -> Postgres memory through assistant-api
```

## Future Workflows

- weekly planning review
- approval-gated text draft flow
- calendar/task cleanup
- richer health and training weekly review with sleep, nutrition, strength, and recovery connectors
- journal synthesis and coaching review
- city/date planning
