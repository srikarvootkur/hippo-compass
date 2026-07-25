-- ghealth is the only Google Health data-plane client.  Raw rows are kept
-- separately from projections so schema additions never discard source data.
CREATE TABLE IF NOT EXISTS ghealth_schema_snapshots (
  id bigserial PRIMARY KEY,
  cli_version text,
  schema_name text NOT NULL,
  schema_json jsonb NOT NULL,
  captured_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (cli_version, schema_name)
);

CREATE TABLE IF NOT EXISTS ghealth_sync_runs (
  id bigserial PRIMARY KEY,
  sync_kind text NOT NULL CHECK (sync_kind IN ('backfill', 'overlap', 'manual')),
  data_type text NOT NULL,
  operation text NOT NULL CHECK (operation IN ('list', 'daily-rollup')),
  from_date date NOT NULL,
  to_date date NOT NULL,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  status text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'failed')),
  page_count integer NOT NULL DEFAULT 0,
  rows_loaded integer NOT NULL DEFAULT 0,
  error text
);

CREATE TABLE IF NOT EXISTS ghealth_ingestion_state (
  state_key text PRIMARY KEY,
  state_value jsonb NOT NULL DEFAULT '{}',
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ghealth_raw_points (
  id bigserial PRIMARY KEY,
  data_type text NOT NULL,
  operation text NOT NULL,
  source text,
  point_time timestamptz,
  point_date date,
  external_id text NOT NULL,
  payload_hash char(64) NOT NULL,
  payload jsonb NOT NULL,
  sync_run_id bigint REFERENCES ghealth_sync_runs(id) ON DELETE SET NULL,
  inserted_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (data_type, operation, external_id, payload_hash)
);
CREATE INDEX IF NOT EXISTS ghealth_raw_points_type_time_idx ON ghealth_raw_points (data_type, point_time DESC);
CREATE INDEX IF NOT EXISTS ghealth_raw_points_type_date_idx ON ghealth_raw_points (data_type, point_date DESC);
CREATE INDEX IF NOT EXISTS ghealth_raw_points_payload_gin_idx ON ghealth_raw_points USING gin (payload);

CREATE TABLE IF NOT EXISTS ghealth_heart_rate_points (
  source text NOT NULL,
  measured_at timestamptz NOT NULL,
  beats_per_minute numeric NOT NULL,
  raw_point_id bigint NOT NULL REFERENCES ghealth_raw_points(id) ON DELETE CASCADE,
  PRIMARY KEY (source, measured_at)
);
CREATE TABLE IF NOT EXISTS ghealth_daily_steps (
  summary_date date PRIMARY KEY,
  step_count bigint NOT NULL,
  raw_point_id bigint NOT NULL REFERENCES ghealth_raw_points(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS ghealth_sleep_sessions (
  external_id text PRIMARY KEY,
  start_time timestamptz NOT NULL,
  end_time timestamptz NOT NULL,
  minutes_asleep integer,
  minutes_awake integer,
  total_minutes integer,
  source text,
  sleep_type text,
  raw_point_id bigint NOT NULL REFERENCES ghealth_raw_points(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS ghealth_exercise_sessions (
  external_id text PRIMARY KEY,
  start_time timestamptz NOT NULL,
  end_time timestamptz NOT NULL,
  source text,
  exercise_type text,
  title text,
  metrics jsonb NOT NULL DEFAULT '{}',
  raw_point_id bigint NOT NULL REFERENCES ghealth_raw_points(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS ghealth_weight_points (
  source text NOT NULL,
  measured_at timestamptz NOT NULL,
  weight_grams numeric NOT NULL,
  raw_point_id bigint NOT NULL REFERENCES ghealth_raw_points(id) ON DELETE CASCADE,
  PRIMARY KEY (source, measured_at)
);

CREATE OR REPLACE VIEW ghealth_daily_context AS
WITH days AS (
  SELECT summary_date FROM ghealth_daily_steps
  UNION SELECT (start_time AT TIME ZONE 'America/New_York')::date FROM ghealth_sleep_sessions
  UNION SELECT (start_time AT TIME ZONE 'America/New_York')::date FROM ghealth_exercise_sessions
  UNION SELECT (measured_at AT TIME ZONE 'America/New_York')::date FROM ghealth_heart_rate_points
  UNION SELECT (measured_at AT TIME ZONE 'America/New_York')::date FROM ghealth_weight_points
)
SELECT d.summary_date,
       st.step_count,
       (SELECT count(*) FROM ghealth_exercise_sessions e WHERE (e.start_time AT TIME ZONE 'America/New_York')::date = d.summary_date) AS exercise_count,
       (SELECT sum(s.minutes_asleep) FROM ghealth_sleep_sessions s WHERE (s.start_time AT TIME ZONE 'America/New_York')::date = d.summary_date) AS minutes_asleep,
       (SELECT avg(h.beats_per_minute) FROM ghealth_heart_rate_points h WHERE (h.measured_at AT TIME ZONE 'America/New_York')::date = d.summary_date) AS average_heart_rate_bpm,
       (SELECT w.weight_grams FROM ghealth_weight_points w WHERE (w.measured_at AT TIME ZONE 'America/New_York')::date = d.summary_date ORDER BY w.measured_at DESC LIMIT 1) AS latest_weight_grams
FROM days d LEFT JOIN ghealth_daily_steps st ON st.summary_date = d.summary_date;
