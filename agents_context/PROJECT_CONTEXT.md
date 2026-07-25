# Hippo Compass / OpenClaw Project Context

This file is a handoff note for continuing development of **Hippo Compass**, a self-hosted personal assistant / health data layer running on a Hetzner VPS with OpenClaw as the first agent shell.

## Server / Repo

- VPS IP: `5.78.196.1`
- SSH: `ssh root@5.78.196.1`
- GitHub repo: `https://github.com/srikarvootkur/hippo-compass`
- VPS repo path: `~/hippo-compass`
- OpenClaw path is probably `/opt/openclaw`

If OpenClaw is missing, locate it with:

```bash
find / -maxdepth 3 -type d -iname "*openclaw*" 2>/dev/null
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}"
```

## Architecture

- Hetzner VPS runs Docker Compose.
- Hippo Compass services:
  - `assistant-api` on `8080`
  - `langgraph-workflows` on `8070`
  - `agents-workflows` on `8090`
  - `workers`
  - `redis`
  - local Postgres/pgvector via `--profile local-db`
- OpenClaw is the agent shell.
- OpenClaw should call Hippo Compass APIs through skills.
- Durable memory/data lives in Postgres, not inside the LLM.

## Docker Commands

Start Hippo Compass:

```bash
cd ~/hippo-compass
docker compose -f infra/docker-compose.yml --env-file .env --profile local-db up -d
```

Rebuild after pulling changes:

```bash
cd ~/hippo-compass
git pull
docker compose -f infra/docker-compose.yml --env-file .env --profile local-db up -d --build assistant-api langgraph-workflows agents-workflows workers
```

Check health:

```bash
curl http://localhost:8080/health
curl http://localhost:8070/health
curl http://localhost:8090/health
```

Start OpenClaw if needed:

```bash
cd /opt/openclaw
docker compose -f docker-compose.yml up -d
```

Restart OpenClaw gateway:

```bash
cd /opt/openclaw
docker compose -f docker-compose.yml restart openclaw-gateway
```

## OpenClaw Model Check

Inside VPS:

```bash
cd /opt/openclaw
docker compose -f docker-compose.yml run --rm openclaw-cli config get agents.defaults.model.primary
docker compose -f docker-compose.yml run --rm openclaw-cli config get agents.defaults.model
```

Raw config:

```bash
docker compose -f docker-compose.yml exec openclaw-gateway sh -lc \
'cat /home/node/.openclaw/openclaw.json | grep -i -A 8 -B 8 model'
```

Logs:

```bash
cd /opt/openclaw
docker compose -f docker-compose.yml logs --tail=120 openclaw-gateway | grep -iE "model|openai|codex|gpt"
```

## Google Health Integration

Implemented a Google Health/Fitbit ingestion layer.

Important endpoints:

```text
GET  /connectors/google-health/catalog
POST /connectors/google-health/configure
GET  /connectors/google-health/oauth/start
GET  /connectors/google-health/oauth/callback
GET  /connectors/google-health/status
POST /connectors/google-health/sync
POST /workflows/health/coach-review
```

OAuth uses SSH tunnel from Mac:

```bash
ssh -L 8080:localhost:8080 root@5.78.196.1
```

Then on VPS:

```bash
cd ~/hippo-compass
key=$(sed -n 's/^ASSISTANT_API_KEY=//p' .env | tail -1)

curl -s -H "X-Assistant-API-Key: $key" \
  http://localhost:8080/connectors/google-health/oauth/start \
  | python3 -m json.tool
```

Open the returned `authorization_url` in Mac browser.

Sync working data types:

```bash
cd ~/hippo-compass
key=$(sed -n 's/^ASSISTANT_API_KEY=//p' .env | tail -1)

curl -s -X POST http://localhost:8080/connectors/google-health/sync \
  -H "Content-Type: application/json" \
  -H "X-Assistant-API-Key: $key" \
  -d '{"data_types":["exercise","sleep","steps","weight"],"lookback_days":30}' \
  | python3 -m json.tool
```

Known successful sync result:

- `status: success`
- `records_seen: 3894`
- `synced_count: 3894`
- `daily_summary_count: 48`
- `failures: {}`

## Health Coach Workflow

Test:

```bash
cd ~/hippo-compass
key=$(sed -n 's/^ASSISTANT_API_KEY=//p' .env | tail -1)

curl -s -X POST http://localhost:8080/workflows/health/coach-review \
  -H "Content-Type: application/json" \
  -H "X-Assistant-API-Key: $key" \
  -d '{"period_days":7,"force_sync":false,"question":"How was my sleep, recovery, activity, nutrition, and training this week?"}' \
  | python3 -m json.tool
```

Health Coach currently works and reads Google Health sleep/steps/weight/exercise from Hippo Compass. It has produced responses with:

- sleep records
- activity summaries
- body/weight metrics
- missing categories
- recommendation + memory IDs

Known polish issue:

- Health Coach may say `0.0 active minutes` even though exercise/activity records exist.
- Need to roll `exercise.active_duration` into daily summaries / active minutes.

## OpenClaw Health Coach Skill

Skill location in repo:

```text
skills/health-coach/
```

Installed OpenClaw copy:

```text
/root/.openclaw/workspace/skills/health-coach/
```

Refresh/reinstall skill on VPS:

```bash
cp -R ~/hippo-compass/skills/health-coach /root/.openclaw/workspace/skills/
chown -R 1000:1000 /root/.openclaw/workspace/skills/health-coach
chmod -R a+rX /root/.openclaw/workspace/skills/health-coach

cd /opt/openclaw
docker compose -f docker-compose.yml run --rm openclaw-cli skills install \
  /home/node/.openclaw/workspace/skills/health-coach \
  --as health-coach \
  --force \
  --agent main

docker compose -f docker-compose.yml restart openclaw-gateway
```

If OpenClaw cannot resolve `assistant-api`, reconnect network:

```bash
docker network connect infra_default openclaw-openclaw-gateway-1 2>/dev/null || true

cd /opt/openclaw
docker compose -f docker-compose.yml exec openclaw-gateway sh -lc \
'getent hosts assistant-api && curl -s http://assistant-api:8080/health'
```

Test skill from inside OpenClaw:

```bash
cd /opt/openclaw
docker compose -f docker-compose.yml exec openclaw-gateway sh -lc \
'HIPPO_COMPASS_API_URL=http://assistant-api:8080 HIPPO_COMPASS_API_KEY=dev-api-key python3 /home/node/.openclaw/workspace/skills/health-coach/scripts/health_coach.py --period-days 7 --no-force-sync --question "Review my sleep, recovery, activity, workouts, and body metrics this week."'
```

Telegram prompt that should work:

```text
Use the health-coach skill. Review my last 7 days of Google Health data, including sleep, activity, workouts, weight/body metrics, missing data, and next actions.
```

## Google Health / Hevy / Strength Training Notes

- Public Google Health API can write exercise sessions, but not true structured lifting sets/reps/weights.
- Google Health AI Coach app can apparently parse Hevy PDF/CSV exports and log sets/reps internally, but that does not mean the public API exposes those details.
- Best architecture:
  - Hippo Compass should be canonical database for strength data.
  - Import Hevy CSV/PDF into Hippo Compass.
  - Store workout/session/exercise/set/reps/weight/RPE/notes/volume in Postgres.
  - Health Coach reads strength data directly from Hippo Compass through `/workflows/health/coach-review`.
  - Optionally write a summarized workout session to Google Health.

## Recent Fixes Already Implemented/Pushed

Several real Google payload bugs were fixed and pushed:

- JSONB sometimes returned as strings; added coercion.
- Timestamp/date strings converted before asyncpg inserts.
- Daily summary dates coerced to `date`.
- Google Health filters updated:
  - interval/session civil time filters
  - sleep uses `:reconcile` and `dataSourceFamily=users/me/dataSourceFamilies/google-wearables`
  - exercise uses `civil_start_time`
- Tests increased to `23 passed`.

## Tests

Run locally:

```bash
PYTHONPATH=services/assistant-api /usr/bin/python3 -m pytest services/assistant-api/tests
```

Known latest result:

- `23 passed`
