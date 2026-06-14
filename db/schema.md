# Database Schema

The first schema is in `db/migrations/001_initial.sql`.

Core tables:

- `source_connections`: connector configuration state.
- `source_records`: raw and normalized records from external apps.
- `source_sync_runs`: sync attempts, imported counts, and connector errors.
- `health_observations`: typed samples, intervals, and daily values for LLM-friendly health queries.
- `health_sessions`: typed exercise, sleep, ECG, hydration, and other session-like records.
- `health_daily_summaries`: daily rollups optimized for coaching, retrieval, and summaries.
- `memories`: semantic memories, preferences, goals, style notes, and embeddings.
- `goals`: active and historical user goals.
- `journal_entries`: life notes and reflections.
- `insights`: extracted observations from journals and source data.
- `recommendations`: assistant-generated suggestions waiting for review.
- `approvals`: queued sensitive actions.
- `tool_runs`: tool execution logs for debugging and traceability.
- `audit_logs`: immutable-ish event history for assistant behavior.

The migration enables `pgvector` through `CREATE EXTENSION IF NOT EXISTS vector;`.
