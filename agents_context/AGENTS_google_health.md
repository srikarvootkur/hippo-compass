# Google Health Data Access for OpenClaw Agents

OpenClaw should use the `ghealth` CLI as the approved interface for Google Health/Fitbit data. Do not call the Google Health API directly unless there is a specific reason to bypass the CLI.

## Purpose

`ghealth` provides structured access to Google Health API v4 data, including:

- heart rate
- steps
- sleep
- exercise
- weight
- SpO2 / oxygen saturation
- HRV
- daily summaries
- calories, distance, activity, hydration, nutrition, and related health records

The CLI handles OAuth, token refresh, pagination, response simplification, schema discovery, and contextual hints.

## Setup Assumptions

The CLI binary should be available in the OpenClaw runtime as either:

```bash
ghealth
```

or at a known path such as:

```bash
/usr/local/bin/ghealth
```

The OAuth config directory should be mounted into the runtime:

```bash
GHEALTH_CONFIG_DIR=/home/openclaw/.config/ghealth
```

Expected files:

```bash
client_secret.json
credentials.json
config.toml
```

Treat these as secrets. Never commit them.

## OAuth Scope Rule

For health data access, use read-only Google Health scopes:

```bash
ghealth auth login --scopes-preset readonly
```

Do not use a token containing `cloud-platform` for normal `ghealth data ...` commands. Google Health data endpoints reject that scope with:

```text
Request contains disallowed OAuth scope(s).
```

Use `cloud-platform` only for webhook/subscriber management, and keep those credentials in a separate config directory such as:

```bash
~/.config/ghealth-webhooks
```

## Discovery Commands

Before assuming available data types or fields, inspect the CLI:

```bash
ghealth schema types
ghealth schema type heart-rate
ghealth schema scopes
ghealth data --help
ghealth data heart-rate --help
ghealth data heart-rate list --help
```

The schema commands are machine-readable and should be preferred over hardcoded assumptions.

## Query Patterns

Use `list` for individual readings and sessions:

```bash
ghealth data heart-rate list --from today --limit 50
ghealth data sleep list --from 2026-07-01 --limit 10000
ghealth data exercise list --from 2026-07-01 --limit 10000
ghealth data weight list --limit 10000
```

Use `daily-rollup` for daily totals:

```bash
ghealth data steps daily-rollup --from 2026-07-01 --to 2026-07-25
ghealth data distance daily-rollup --from 2026-07-01 --to 2026-07-25
ghealth data total-calories daily-rollup --from 2026-07-01 --to 2026-07-25
```

Important: `steps list` can return time intervals without actual step counts. For step totals, use `steps daily-rollup`.

## Response Shape

Read operations return JSON with rows under `dataPoints`:

```json
{
  "dataPoints": [],
  "nextPageToken": "optional"
}
```

If `nextPageToken` exists, repeat the same command with:

```bash
--page-token '<token>'
```

Continue until `nextPageToken` is absent.

## Data Freshness

Fitbit/Google Health data may lag behind the current time. This is normal. Device data can appear locally before it syncs to Fitbit cloud and then into Google Health.

To check the newest known heart-rate point:

```bash
ghealth data heart-rate list --from today --limit 1
```

Do not assume missing recent records mean the ingestion code is broken.

## Timezone

Set and verify timezone explicitly:

```bash
ghealth user settings get
ghealth config set timezone America/New_York
```

In Docker, set:

```bash
TZ=America/New_York
```

Use exact dates in scheduled jobs when possible. `today` and `yesterday` depend on the configured timezone.

## Postgres Integration Guidance

Prefer a two-layer database model:

1. Raw JSONB table for all `ghealth` rows.
2. Typed tables or views for common assistant queries.

Minimum raw tables:

```sql
create table ghealth_sync_runs (
  id bigserial primary key,
  data_type text not null,
  operation text not null,
  from_ts timestamptz,
  to_ts timestamptz,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'running',
  rows_loaded integer not null default 0,
  error text
);

create table ghealth_raw_points (
  id bigserial primary key,
  data_type text not null,
  operation text not null,
  source text,
  point_time timestamptz,
  point_date date,
  external_id text,
  payload jsonb not null,
  sync_run_id bigint references ghealth_sync_runs(id),
  inserted_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index ghealth_raw_points_type_time_idx
on ghealth_raw_points (data_type, point_time desc);

create index ghealth_raw_points_type_date_idx
on ghealth_raw_points (data_type, point_date desc);

create index ghealth_raw_points_payload_gin_idx
on ghealth_raw_points using gin (payload);
```

Suggested typed tables/views:

- `heart_rate_points`
- `daily_steps`
- `sleep_sessions`
- `exercise_sessions`
- `daily_health_summaries`

## Ingestion Strategy

For initial backfill:

- Pull historical data in week-sized or month-sized windows.
- Page through all `nextPageToken` results.
- Insert raw rows first.
- Populate typed tables from raw rows.

For ongoing sync:

- Poll a recent overlapping window, such as the last 6 to 24 hours.
- Overlap is important because Fitbit/Google Health data can arrive late.
- Upsert/dedupe rows by type, timestamp/date, source/id if present, and payload hash.

Start with these high-value types:

```text
heart-rate
steps daily-rollup
sleep
exercise
weight
daily-resting-heart-rate
heart-rate-variability
oxygen-saturation
```

## Safety

- Never commit OAuth credentials.
- Give OpenClaw read-only database access where possible.
- Let the ingestion worker own database writes.
- Keep `cloud-platform` credentials separate from health-data credentials.
- Prefer read-only health scopes unless write access is explicitly needed.

