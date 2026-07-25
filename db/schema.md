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

Google Health tables added by `004_ghealth_ingestion.sql`:

- `ghealth_schema_snapshots`: CLI-discovered schema contracts used by the ingest worker.
- `ghealth_sync_runs`: per-type backfill/overlap execution state and errors.
- `ghealth_raw_points`: original `ghealth --raw` JSONB records and payload hashes.
- `ghealth_heart_rate_points`, `ghealth_daily_steps`, `ghealth_sleep_sessions`,
  `ghealth_exercise_sessions`, and `ghealth_weight_points`: verified typed projections.
- `ghealth_daily_context`: timezone-aware assistant query view.

The migration enables `pgvector` through `CREATE EXTENSION IF NOT EXISTS vector;`.
