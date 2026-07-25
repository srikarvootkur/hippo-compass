# Context: Google Health CLI for OpenClaw + Postgres

This file is a handoff note for setting up `google-health-cli` on a Hetzner VPS, making it available to OpenClaw, and loading Google Health/Fitbit data into Postgres tables.

## What this repo is

`ghealth` is a Go CLI for the Google Health API v4. It handles OAuth, pagination, response simplification, rollups, CSV/JSON output, and schema discovery.

Local repo:

```bash
/Users/srikarvootkur/Documents/GitHub/google-health-cli
```

Build:

```bash
go build -o ghealth .
```

Important discovery commands:

```bash
./ghealth schema types
./ghealth schema type heart-rate
./ghealth schema scopes
./ghealth data --help
```

## Current local finding

The CLI is working locally after re-authenticating with health-data scopes only:

```bash
./ghealth auth login --scopes-preset readonly
```

The earlier failure was:

```json
{
  "status": 403,
  "message": "Request contains disallowed OAuth scope(s)."
}
```

Cause: the default profile/token included `cloud-platform` together with Google Health scopes. Google Health data-plane endpoints reject tokens containing `cloud-platform`.

Rule:

- Use health-data scopes for `ghealth data ...`
- Use `cloud-platform` only for `ghealth webhooks ...`
- Keep webhook credentials in a separate config dir, for example `~/.config/ghealth-webhooks`

For OpenClaw’s personal assistant use case, start with:

```bash
ghealth auth login --scopes-preset readonly
```

Do not run plain `ghealth auth login` if the active profile still contains `cloud-platform`, because it will reuse the bad scope list.

## Important files

By default, `ghealth` uses:

```bash
~/.config/ghealth/client_secret.json
~/.config/ghealth/credentials.json
~/.config/ghealth/config.toml
```

These contain OAuth client secrets and refresh tokens. Treat them as secrets.

For Docker, mount them read-only if possible:

```yaml
volumes:
  - ./ghealth-config:/home/openclaw/.config/ghealth:ro
```

If the ingest process must refresh tokens and rewrite `credentials.json`, the config directory needs to be writable by the container user. Prefer a private Docker volume or a host directory with strict permissions.

## Headless VPS OAuth setup

On the VPS/container, build or install `ghealth`, then configure it with non-interactive auth:

```bash
ghealth setup \
  --project-id "$GOOGLE_CLOUD_PROJECT_ID" \
  --client-secret /run/secrets/client_secret.json \
  --scopes-preset readonly \
  --skip-enable-api \
  --no-prompt \
  --non-interactive-auth
```

It will print an `auth_url`. Open that URL in a browser on any machine, approve access, then copy either the full redirected URL or the `code` query parameter.

Complete on the VPS:

```bash
ghealth auth login --complete '<code-or-redirect-url>'
```

Verify:

```bash
ghealth auth status
ghealth auth status --validate
ghealth data heart-rate list --from today --limit 1
```

Alternative: authenticate locally, then export/import credentials:

```bash
# local authenticated machine
./ghealth auth export > ghealth-creds.json

# VPS/container, with same client_secret configured
ghealth auth import --file ghealth-creds.json
```

## Data availability notes

The API is not necessarily real-time. Fitbit data may lag behind the current time due to Fitbit device sync, Fitbit cloud sync, or Google Health ingestion lag.

Example observed locally on 2026-07-25:

```bash
./ghealth data heart-rate list --from today --limit 50
```

Newest returned Fitbit point was around `10:48 AM -04:00` when local time was around `11:21 AM -04:00`, so about 30 minutes behind.

For freshness checks:

```bash
ghealth data heart-rate list --from today --limit 1
```

## Available data types

There are 40 registered data types. Use `ghealth schema types` as the source of truth. Important ones for a personal assistant:

- `heart-rate`
- `steps`
- `sleep`
- `exercise`
- `weight`
- `body-fat`
- `height`
- `oxygen-saturation`
- `heart-rate-variability`
- `daily-resting-heart-rate`
- `daily-heart-rate-variability`
- `daily-oxygen-saturation`
- `daily-respiratory-rate`
- `daily-vo2-max`
- `distance`
- `total-calories`
- `active-energy-burned`
- `basal-energy-burned`
- `active-zone-minutes`
- `activity-level`
- `sedentary-period`
- `nutrition-log`
- `hydration-log`

Special types:

- `electrocardiogram` requires `ecg.readonly`
- `irregular-rhythm-notification` requires `irn.readonly`
- `food` and `food-measurement-unit` are reference catalogs, not time-series data

## Operation choice

Use `list` for individual readings and sessions:

```bash
ghealth data heart-rate list --from 2026-07-01 --limit 10000
ghealth data sleep list --from 2026-07-01 --limit 10000
ghealth data exercise list --from 2026-07-01 --limit 10000
```

Use `daily-rollup` for daily totals:

```bash
ghealth data steps daily-rollup --from 2026-07-01 --to 2026-07-25
ghealth data distance daily-rollup --from 2026-07-01 --to 2026-07-25
ghealth data total-calories daily-rollup --from 2026-07-01 --to 2026-07-25
```

Gotcha: `steps list` may return intervals without actual step counts. For totals, use `steps daily-rollup`.

Missing days are not zero. For rollup-style data, an absent date usually means no synced/worn data, not a true zero. A returned `"countSum": "0"` is a real zero.

## Pagination

All read outputs have this shape:

```json
{
  "dataPoints": [],
  "nextPageToken": "optional"
}
```

If `nextPageToken` exists, call the same command again with:

```bash
--page-token '<token>'
```

For high-volume data such as heart rate, page until `nextPageToken` is absent.

## Recommended Postgres design

Start simple and preserve raw source rows. Avoid over-modeling every type on day one.

Recommended base tables:

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

create unique index ghealth_raw_points_dedupe_idx
on ghealth_raw_points (
  data_type,
  operation,
  coalesce(external_id, ''),
  coalesce(point_time, 'epoch'::timestamptz),
  coalesce(point_date, '1970-01-01'::date),
  md5(payload::text)
);

create index ghealth_raw_points_type_time_idx
on ghealth_raw_points (data_type, point_time desc);

create index ghealth_raw_points_type_date_idx
on ghealth_raw_points (data_type, point_date desc);

create index ghealth_raw_points_payload_gin_idx
on ghealth_raw_points using gin (payload);
```

Then add typed tables/views for the hot paths OpenClaw will query often:

```sql
create table heart_rate_points (
  time timestamptz primary key,
  beats_per_minute integer not null,
  source text,
  raw_point_id bigint references ghealth_raw_points(id)
);

create table daily_steps (
  date date primary key,
  count_sum bigint,
  raw_point_id bigint references ghealth_raw_points(id)
);

create table sleep_sessions (
  id bigserial primary key,
  start_time timestamptz,
  end_time timestamptz,
  minutes_asleep integer,
  minutes_awake integer,
  source text,
  raw_point_id bigint references ghealth_raw_points(id)
);

create table exercise_sessions (
  external_id text primary key,
  start_time timestamptz,
  end_time timestamptz,
  exercise_type text,
  calories_kcal numeric,
  avg_heart_rate_bpm integer,
  source text,
  raw_point_id bigint references ghealth_raw_points(id)
);
```

The raw JSONB table gives flexibility when fields differ by type or Google changes shapes. Typed tables make common assistant queries fast and easy.

## Ingestion approach

Suggested worker behavior:

1. Maintain a per-data-type high-water mark in Postgres.
2. For backfill, pull month-sized or week-sized windows.
3. For ongoing sync, poll recent windows with overlap, e.g. last 6 to 24 hours, to catch late-arriving Fitbit data.
4. Upsert/dedupe rows by type, timestamp/date, source/id if present, and payload hash.
5. Load raw JSONB first, then populate typed tables from raw rows.

Example commands for a bootstrap backfill:

```bash
ghealth data heart-rate list --from 2026-01-01 --to 2026-02-01 --limit 10000
ghealth data sleep list --from 2026-01-01 --to 2026-02-01 --limit 10000
ghealth data exercise list --from 2026-01-01 --to 2026-02-01 --limit 10000
ghealth data steps daily-rollup --from 2026-01-01 --to 2026-02-01
ghealth data distance daily-rollup --from 2026-01-01 --to 2026-02-01
ghealth data total-calories daily-rollup --from 2026-01-01 --to 2026-02-01
```

For ongoing sync:

```bash
ghealth data heart-rate list --from yesterday --limit 10000
ghealth data sleep list --from 2026-07-24 --limit 10000
ghealth data exercise list --from 2026-07-24 --limit 10000
ghealth data steps daily-rollup --from 2026-07-24 --to 2026-07-26
```

Use exact dates in scheduled jobs instead of relying only on `today`/`yesterday`, unless the container timezone is explicitly configured.

## Timezone

Set the profile timezone explicitly:

```bash
ghealth user settings get
ghealth config set timezone America/New_York
```

This matters because `--from today` and `daily-rollup` use local/civil-day boundaries.

In Docker, also set:

```yaml
environment:
  TZ: America/New_York
```

## Sizing estimate

Heart rate will dominate storage.

A Fitbit heart-rate stream can be sampled every few seconds. If sampled every 3 seconds:

```text
~28,800 rows/day
~10.5 million rows/year
```

Rough Postgres storage for heart rate:

```text
normal typed table + indexes: maybe 1-3 GB/year
raw JSONB plus indexes: maybe 2-6+ GB/year
```

The rest of the data is usually much smaller:

- steps daily totals: one row/day
- sleep: one or a few sessions/day
- exercise: usually a few sessions/day
- daily summaries: one row/day per type
- weight/body metrics: sparse

To estimate empirically:

```bash
ghealth data heart-rate list --from today --limit 10000 > hr_today.json
jq '.dataPoints | length' hr_today.json
wc -c hr_today.json
```

Then multiply rows/day and bytes/row by the intended retention period, adding headroom for Postgres indexes and JSONB overhead.

## Docker/OpenClaw integration sketch

OpenClaw can call the `ghealth` binary directly, or a small ingest service can call it and write to Postgres.

Recommended layout:

```text
openclaw/
  docker-compose.yml
  services/
    ghealth-ingest/
      Dockerfile
      ingest.py or ingest.ts
  secrets/
    ghealth-config/
      client_secret.json
      credentials.json
      config.toml
```

Compose services:

- `postgres`
- `openclaw`
- `ghealth-ingest`

The ingest service needs:

```bash
DATABASE_URL=postgresql://...
GHEALTH_CONFIG_DIR=/home/openclaw/.config/ghealth
TZ=America/New_York
```

Health check commands:

```bash
ghealth auth status --validate
ghealth data heart-rate list --from today --limit 1
psql "$DATABASE_URL" -c 'select count(*) from ghealth_raw_points;'
```

## Security notes

- Do not commit `client_secret.json`, `credentials.json`, `.env`, or exported credential files.
- Restrict mounted config directory permissions.
- Use read-only Google Health scopes unless write access is explicitly needed.
- Keep `cloud-platform` out of the default health-data config.
- Consider giving OpenClaw database read-only access to health tables/views, while the ingest worker owns writes.

## Good first milestone

1. Build `ghealth` in Docker.
2. Mount a working `GHEALTH_CONFIG_DIR`.
3. Verify `ghealth data heart-rate list --from today --limit 1`.
4. Create `ghealth_raw_points` and `ghealth_sync_runs`.
5. Ingest only `heart-rate`, `steps daily-rollup`, `sleep`, and `exercise`.
6. Add typed tables/views for those four.
7. Add a scheduled recent-window sync every 15-60 minutes with overlap.

