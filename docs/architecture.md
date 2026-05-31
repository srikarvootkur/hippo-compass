# Architecture

The assistant is split into replaceable layers:

1. OpenClaw is the first agent shell.
2. `assistant-api` is the stable capability boundary.
3. LangGraph powers durable backend workflows.
4. OpenAI Agents SDK powers focused specialist agents.
5. Managed Postgres with pgvector stores durable memory.
6. External connectors import data into normalized source records.
7. Synthetic context and eval files make public demos possible without private data.

OpenClaw should call API tools. It should not directly hold database credentials, source credentials, or durable memory.

## Runtime Flow

```text
User
  -> OpenClaw / Telegram / Web
  -> assistant-api
  -> langgraph-workflows / workers
  -> agents-workflows for focused specialist calls
  -> managed Postgres + pgvector
  -> approval queue for sensitive actions
```

## Portability Rule

Any future agent framework should be able to call the same assistant API. This keeps memory and integrations independent from OpenClaw, OpenAI, Claude, Gemini, or any specific UI.

## Useful API Concepts

- Journal entries create durable source context.
- Memories store reusable facts, preferences, themes, and style notes.
- Recommendations are suggestions that can be reviewed before action.
- Approvals gate sensitive actions.
- Tool runs make agent behavior inspectable when something goes sideways.

## Workflow Framework Choice

LangGraph is the default long-term workflow engine because Hippo Compass needs durable state, human-in-the-loop approvals, resumable flows, retries, and multi-step background jobs.

OpenAI Agents SDK stays in the stack for focused OpenAI-native specialist agents where lightweight handoffs, tools, guardrails, and tracing are useful.

The current Cronometer path is:

```text
assistant-api
  -> langgraph-workflows
  -> agents-workflows nutrition specialist
  -> response with recommendation + memory candidates
```
