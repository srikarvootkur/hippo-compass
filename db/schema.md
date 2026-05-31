# Database Schema

The first schema is in `db/migrations/001_initial.sql`.

Core tables:

- `source_connections`: connector configuration state.
- `source_records`: raw and normalized records from external apps.
- `memories`: semantic memories, preferences, goals, style notes, and embeddings.
- `goals`: active and historical user goals.
- `journal_entries`: life notes and reflections.
- `insights`: extracted observations from journals and source data.
- `recommendations`: assistant-generated suggestions waiting for review.
- `approvals`: queued sensitive actions.
- `tool_runs`: tool execution logs for debugging and traceability.
- `audit_logs`: immutable-ish event history for assistant behavior.

The migration enables `pgvector` through `CREATE EXTENSION IF NOT EXISTS vector;`.
