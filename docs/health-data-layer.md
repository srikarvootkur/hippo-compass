# Hippo Compass Health Data Layer

The Health Data Layer is the standalone-feeling ingestion module inside Hippo Compass. It pulls health data into Postgres in a shape that is useful for LLM summaries, coaching, habit review, and future agent workflows.

The v1 product is single-user and self-hosted.

## Architecture

```text
Google Health / CSV exports
  -> assistant-api connectors
  -> source_records raw storage
  -> typed health tables
  -> daily summaries
  -> health coach workflow
  -> OpenClaw skill / future agents
```

The important boundary: connectors store source data and normalized facts. The LLM reads summaries and typed facts; it should not be the database.

## Storage Model

- `source_records`: raw payloads plus normalized JSON. This is the bronze/audit layer.
- `source_sync_runs`: sync attempts, counts, failures, and timing.
- `health_observations`: samples, intervals, and daily values such as steps, heart rate, HRV, VO2 max, weight, oxygen saturation, respiratory rate, and nutrition samples.
- `health_sessions`: session-like records such as exercise, sleep, ECG, hydration, Hevy set rows, and imported workouts.
- `health_daily_summaries`: daily rollups for fast coaching and LLM context.

Typed rows link back to `source_records.id` so you can debug any summary later.

## CLI

Run CLI commands from the repo root:

```bash
python3 tools/hippo_health.py --help
```

Set the API location and key when calling a running server:

```bash
export HIPPO_COMPASS_API_URL=http://localhost:8080
export HIPPO_COMPASS_API_KEY=change-me-local-dev
```

On the VPS/OpenClaw Docker network, the API URL is usually:

```bash
export HIPPO_COMPASS_API_URL=http://assistant-api:8080
```

## Google Health Setup

Use Google’s official docs as the source of truth:

- Data types: <https://developers.google.com/health/data-types>
- Scopes: <https://developers.google.com/health/scopes>
- Endpoints: <https://developers.google.com/health/endpoints>
- First API call codelab: <https://developers.google.com/health/codelabs/make-your-first-api-call>

In Google Cloud:

1. Create or select a Google Cloud project.
2. Enable **Google Health API**.
3. Configure OAuth consent.
4. Add yourself as a test user while the app is in Testing.
5. Create OAuth credentials:
   - Application type: Web application
   - Authorized JavaScript origin:

     ```text
     http://localhost:8080
     ```

   - Authorized redirect URI:

     ```text
     http://localhost:8080/connectors/google-health/oauth/callback
     ```

6. Add the Google Health readonly scopes you plan to use.

For all readable Google Health categories, Hippo Compass uses these readonly scope groups:

```text
https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly
https://www.googleapis.com/auth/googlehealth.ecg.readonly
https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly
https://www.googleapis.com/auth/googlehealth.irn.readonly
https://www.googleapis.com/auth/googlehealth.location.readonly
https://www.googleapis.com/auth/googlehealth.nutrition.readonly
https://www.googleapis.com/auth/googlehealth.profile.readonly
https://www.googleapis.com/auth/googlehealth.settings.readonly
https://www.googleapis.com/auth/googlehealth.sleep.readonly
```

Run setup:

```bash
python3 tools/hippo_health.py setup
```

Restart `assistant-api` after changing `.env`.

Configure all Google Health data types:

```bash
python3 tools/hippo_health.py google configure --data-types all --schedule manual
```

Start OAuth:

```bash
python3 tools/hippo_health.py google connect
```

Open the returned `authorization_url`, approve access, then check:

```bash
python3 tools/hippo_health.py google status
```

Sync:

```bash
python3 tools/hippo_health.py sync --data-types all --lookback-days 30
```

## Data Type Selection

List the current catalog:

```bash
python3 tools/hippo_health.py google catalog
```

Select a smaller set:

```bash
python3 tools/hippo_health.py google configure \
  --data-types exercise sleep steps heart-rate daily-resting-heart-rate weight \
  --schedule daily
```

Google’s docs note that endpoint data type names use kebab-case, while filter names use snake_case. Hippo Compass stores both in the catalog.

## Recurring Sync

The worker checks the Google Health connector schedule and can trigger syncs:

```bash
python3 tools/hippo_health.py schedule daily
python3 tools/hippo_health.py schedule weekly
python3 tools/hippo_health.py schedule off
```

Public default: manual sync.

Suggested personal setup: daily Google Health sync, weekly CSV imports from Hevy/Cronometer.

## CSV Imports

Hevy:

```bash
python3 tools/hippo_health.py import-csv --source hevy --file /path/to/hevy.csv
```

Cronometer:

```bash
python3 tools/hippo_health.py import-csv --source cronometer --file /path/to/cronometer.csv
```

CSV import is intentionally flexible in v1. It stores the full source row in `source_records.raw_payload`, then normalizes common fields:

- Hevy: exercise name, workout title, set index/type, reps, weight, volume, duration, distance, notes.
- Cronometer: date, food, meal/group, calories, protein, carbs, fat, fiber.

## Health Coach

Use the unified endpoint:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-Assistant-API-Key: YOUR_ASSISTANT_API_KEY" \
  -d '{"period_days":7,"force_sync":true,"question":"How was my sleep, recovery, activity, nutrition, and training this week?"}' \
  http://localhost:8080/workflows/health/coach-review
```

The OpenClaw `health-coach` skill calls this endpoint.

The coach separates:

- activity
- sleep/recovery
- heart metrics
- body metrics
- nutrition
- strength training
- unknown or missing data

This is wellness coaching, not diagnosis or treatment advice.

## Data Availability

Google Health can only return data that is available to the user’s Google/Fitbit account. Fitbit device data must sync through the Fitbit app or Google pathway before the API can return it.

If a data type fails during sync, Hippo Compass records the failure in `source_sync_runs.metadata.failures` and continues syncing other selected data types.
