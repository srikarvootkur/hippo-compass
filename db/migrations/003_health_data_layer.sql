CREATE TABLE IF NOT EXISTS source_sync_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_name text NOT NULL,
  data_types text[] NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'running',
  started_at timestamptz NOT NULL DEFAULT now(),
  ended_at timestamptz,
  records_seen integer NOT NULL DEFAULT 0,
  records_imported integer NOT NULL DEFAULT 0,
  error text,
  metadata jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS health_observations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_record_id uuid REFERENCES source_records(id) ON DELETE CASCADE,
  source_name text NOT NULL,
  data_type text NOT NULL,
  external_id text NOT NULL,
  category text NOT NULL,
  observed_at timestamptz,
  start_time timestamptz,
  end_time timestamptz,
  value_numeric double precision,
  value_text text,
  unit text,
  summary jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_name, data_type, external_id)
);

CREATE TABLE IF NOT EXISTS health_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_record_id uuid REFERENCES source_records(id) ON DELETE CASCADE,
  source_name text NOT NULL,
  data_type text NOT NULL,
  external_id text NOT NULL,
  category text NOT NULL,
  session_type text,
  title text,
  start_time timestamptz,
  end_time timestamptz,
  metrics jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_name, data_type, external_id)
);

CREATE TABLE IF NOT EXISTS health_daily_summaries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_name text NOT NULL,
  summary_date date NOT NULL,
  category text NOT NULL,
  metrics jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_name, summary_date, category)
);

CREATE INDEX IF NOT EXISTS idx_source_sync_runs_source_started ON source_sync_runs (source_name, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_observations_type_time ON health_observations (data_type, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_observations_category_time ON health_observations (category, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_sessions_type_time ON health_sessions (data_type, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_health_sessions_category_time ON health_sessions (category, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_health_daily_summaries_date ON health_daily_summaries (summary_date DESC);
