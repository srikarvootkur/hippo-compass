# Hippo Compass

Hippo Compass is my personal assistant infrastructure project.

The goal is pretty simple: I want an assistant that can remember useful context about my life, pull data from the apps I use, help me make better decisions, and stay portable so I am not locked into one agent framework forever.

This repo is the starting point. It runs OpenClaw as the first assistant shell, uses LangGraph for durable workflows, uses OpenAI Agents SDK for focused specialist agents, and stores durable memory in Postgres with `pgvector`.

## What This Is

Hippo Compass is meant to become:

- a personal memory layer
- a task/calendar/reminder/list assistant
- a health and fitness review system
- a writing-style-aware text drafting assistant
- a life/journal/coach context system
- a portable backend that other agent tools can call later

The important design rule: **the LLM is not the memory store**.

The assistant can use OpenAI, OpenClaw, Claude, Gemini, Codex, or something else later. The durable memory should live in a normal database that I control.

## Current Stack

- **Hetzner VPS** for hosting the app runtime.
- **Managed Postgres with pgvector** for memory, ideally Supabase or Neon for v1.
- **OpenClaw** as the first agent shell.
- **LangGraph** for durable workflows, approvals, retries, and long-running assistant flows.
- **OpenAI Agents SDK** for focused specialist agents like nutrition review and writing-style drafting.
- **FastAPI** for the assistant backend.
- **Docker Compose** for deployment.
- **Redis** for background jobs and queues.
- **Caddy** for HTTPS.
- **Google Health API connector** for read-only Fitbit-backed activity/fitness imports.

## Repo Layout

```text
docs/                  Architecture and setup docs
context/               Public-safe synthetic context examples
evals/                 Synthetic behavior/evaluation cases
infra/                 Docker Compose, Caddy, env template
services/
  assistant-api/       Main API for memory, approvals, and workflows
  langgraph-workflows/ Durable workflow orchestration service
  agents-workflows/    OpenAI Agents SDK specialist workflow service
  workers/             Background worker skeleton
  mac-bridge/          Future local-only Mac/iMessage bridge
skills/                OpenClaw workspace skills that call the assistant API
templates/             Starter templates for new OpenClaw skills
db/migrations/         Postgres and pgvector schema
prompts/               Starting prompts
runbooks/              Ops notes and future migration guides
```

## Quick Local Setup

This gets the services running locally with mock workflows.

1. Install Docker Desktop if you are running this on your Mac.

   You do not need Docker Desktop on a Linux VPS. On Hetzner, install Docker Engine and the Docker Compose plugin.

2. Copy the environment template:

   ```bash
   cp infra/env.example .env
   ```

3. Edit `.env`.

   For local development, the default `DATABASE_URL` points to the optional local Postgres container. You can leave `OPENAI_API_KEY` empty at first because the Cronometer workflow has a mock mode.

4. Start the local stack with local Postgres:

   ```bash
   docker compose -f infra/docker-compose.yml --env-file .env --profile local-db up --build
   ```

5. Check that the services are alive:

   ```bash
   curl http://localhost:8080/health
   curl http://localhost:8070/health
   curl http://localhost:8090/health
   ```

6. Try the mock Cronometer workflow:

   ```bash
   curl -X POST http://localhost:8080/workflows/cronometer/daily-review \
     -H "Content-Type: application/json" \
     -H "X-Assistant-API-Key: change-me-local-dev" \
     -d '{"use_mock_data": true}'
   ```

## Managed Postgres + pgvector Setup

For production, I want the database managed separately from the Hetzner VPS. Supabase or Neon is the simplest v1 choice.

### Option A: Supabase

1. Create a new Supabase project.
2. Open the SQL editor.
3. Run:

   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

4. Run the migration in `db/migrations/001_initial.sql`.
5. Copy the pooled or direct Postgres connection string.
6. Set `DATABASE_URL` in `.env` on the server.

### Option B: Neon

1. Create a new Neon project.
2. Open the SQL editor.
3. Run:

   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

4. Run the migration in `db/migrations/001_initial.sql`.
5. Copy the connection string.
6. Set `DATABASE_URL` in `.env` on the server.

## Hetzner Setup

The detailed version is in [docs/hetzner-setup.md](docs/hetzner-setup.md).

Short version:

1. Create a Hetzner Cloud VPS with Ubuntu LTS.
2. Add your SSH key.
3. Optional: point DNS records at the server if you already own a domain:

   ```text
   assistant.yourdomain.com -> server IPv4
   openclaw.yourdomain.com  -> server IPv4
   ```

   If you do not own a domain yet, skip DNS for now and use SSH tunnels while building.

4. SSH in:

   ```bash
   ssh root@YOUR_SERVER_IP
   ```

5. Install Docker:

   ```bash
   apt update
   apt install -y ca-certificates curl git ufw
   install -m 0755 -d /etc/apt/keyrings
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
   chmod a+r /etc/apt/keyrings/docker.asc
   echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
   apt update
   apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   ```

6. Set up the firewall:

   ```bash
   ufw allow OpenSSH
   ufw allow 80/tcp
   ufw allow 443/tcp
   ufw --force enable
   ```

7. Clone the repo:

   ```bash
   git clone https://github.com/srikarvootkur/hippo-compass.git
   cd hippo-compass
   cp infra/env.example .env
   ```

   If the repo is private, use a GitHub deploy key or a fine-grained token with `Contents: Read-only`. Do not commit tokens or keys to this repo.

8. Edit `.env` with real values:

   ```bash
   nano .env
   ```

   At minimum set:

   ```text
   ASSISTANT_DOMAIN=assistant.yourdomain.com
   OPENCLAW_DOMAIN=openclaw.yourdomain.com
   ASSISTANT_API_KEY=a-long-random-secret
   DATABASE_URL=your-managed-postgres-url
   OPENAI_API_KEY=your-openai-api-key
   ```

9. Start the backend services first.

   For a first VPS setup without managed Postgres yet, use the local Postgres profile:

   ```bash
   docker compose -f infra/docker-compose.yml --env-file .env --profile local-db up -d --build
   ```

   If you already configured managed Postgres, omit `--profile local-db`:

   ```bash
   docker compose -f infra/docker-compose.yml --env-file .env up -d --build
   ```

10. Check status locally on the VPS:

   ```bash
   docker compose -f infra/docker-compose.yml --env-file .env ps
   curl http://localhost:8080/health
   curl http://localhost:8070/health
   curl http://localhost:8090/health
   ```

11. Try the mock workflow:

   ```bash
   curl -X POST http://localhost:8080/workflows/cronometer/daily-review \
     -H "Content-Type: application/json" \
     -H "X-Assistant-API-Key: your-secret" \
     -d '{"use_mock_data": true}'
   ```

12. Add DNS/Caddy and OpenClaw after the backend is healthy.

13. Add Google Health after the backend is healthy if you want Fitbit-backed activity data. See [docs/google-health-connector.md](docs/google-health-connector.md).

## Connecting OpenClaw

OpenClaw should call the assistant API as a tool server.

For first setup, keep OpenClaw simple:

- Provider: OpenAI.
- Search provider: DuckDuckGo or skip.
- Channel: Telegram is fine if you already have a bot token. Otherwise skip.
- Skills: skip until the dashboard/provider work.
- Hooks: skip until you need custom guardrails or approval automation.

Use the current OpenClaw Docker setup script from the OpenClaw repo root:

```bash
./scripts/docker/setup.sh
```

Minimum endpoints:

- `POST /memory/search`
- `POST /memory/write`
- `POST /journal_entries`
- `GET /recommendations`
- `POST /recommendations`
- `POST /approvals`
- `POST /tool_runs`
- `POST /workflows/cronometer/daily-review`
- `POST /workflows/google-health/coach-review`

Use this header:

```text
X-Assistant-API-Key: your-secret
```

The point is to keep OpenClaw replaceable. If I switch to another agent framework later, that tool should call the same API and database.

Workflow rule:

- `assistant-api` is the public tool boundary.
- `langgraph-workflows` owns durable workflow orchestration.
- `agents-workflows` owns focused OpenAI-native specialist tasks.
- Postgres remains the source of truth.

Recommended order:

1. Get `assistant-api`, `langgraph-workflows`, `agents-workflows`, Redis, and Postgres healthy.
2. Add DNS/Caddy if you want public HTTPS URLs.
3. Install and configure OpenClaw.

Without DNS, access services from your Mac with an SSH tunnel:

```bash
ssh -L 8080:localhost:8080 -L 8070:localhost:8070 -L 8090:localhost:8090 root@YOUR_SERVER_IP
```

Then use `http://localhost:8080` from your Mac while the tunnel is open.

OpenClaw runs in its own Docker Compose project. Without DNS/Caddy, connect it to Hippo Compass with a shared Docker network:

```bash
docker network create hippo-compass-net
docker network connect --alias assistant-api hippo-compass-net infra-assistant-api-1
docker network connect hippo-compass-net openclaw-openclaw-gateway-1
```

Then OpenClaw should use:

```text
HIPPO_COMPASS_API_URL=http://assistant-api:8080
HIPPO_COMPASS_API_KEY=your-secret
```

If OpenClaw errors on `openai/gpt-5.3-codex`, switch to a regular OpenAI model:

```bash
cd /opt/openclaw
docker compose -f /opt/openclaw/docker-compose.yml run --rm openclaw-cli config set agents.defaults.model.primary openai/gpt-5.4-mini
docker compose -f /opt/openclaw/docker-compose.yml restart openclaw-gateway
```

## Safety Defaults

This project should be private-first and approval-first.

The assistant can eventually update low-risk things like tasks, notes, and calendar items. But it should ask before doing anything sensitive:

- sending texts
- booking reservations
- purchases
- banking or money movement
- external posts
- deleting data

iMessage should run through a local Mac bridge later. The Hetzner server should not directly touch the Messages database.

## Publishing Notes

If this repo ever becomes public:

- keep `.env` private
- keep API keys out of git
- use example configs only
- make all integrations opt-in
- document what data each connector stores
- keep dangerous actions behind approvals
- keep real profile/journal/style notes out of `context/`
- use synthetic `evals/` cases for demos and regression checks

## Building New Skills

New assistant abilities should usually be built as a Hippo Compass API/workflow first, then exposed to OpenClaw through a thin skill.

Start here:

- [runbooks/adding-new-skill.md](runbooks/adding-new-skill.md)
- [skills/README.md](skills/README.md)
- [templates/openclaw-skill](templates/openclaw-skill)

The short version: keep credentials, memory, and durable logic behind `assistant-api`; keep OpenClaw skills small, testable, and easy to reinstall.

## Push To GitHub

The GitHub repo already exists at:

```text
https://github.com/srikarvootkur/hippo-compass.git
```

When ready, run:

```bash
git remote add origin https://github.com/srikarvootkur/hippo-compass.git
git branch -M main
git add .
git commit -m "Initial Hippo Compass assistant scaffold"
git push -u origin main
```

If `origin` already exists, use:

```bash
git remote set-url origin https://github.com/srikarvootkur/hippo-compass.git
git push -u origin main
```

## Next Build Steps

1. Push this scaffold to GitHub.
2. Pick Supabase or Neon and run the migration.
3. Bring up the stack locally with Docker.
4. Deploy to Hetzner.
5. Connect OpenClaw to the assistant API.
6. Replace mock Cronometer data with the first real connector.

## Google Health Connector

The Google Health connector is the first real health-data import path. It uses OAuth, stores tokens in Postgres, and imports `exercise` data points into `source_records`.

See [docs/google-health-connector.md](docs/google-health-connector.md).

The connector currently supports:

- OAuth start/callback/status
- access-token refresh through the saved refresh token
- read-only `exercise` data point sync
- idempotent upsert into `source_records`
- normalized exercise fields for later LangGraph summaries

## Google Health Coach

The Google Health Coach workflow exposes a single OpenClaw skill for wellness coaching from Google Health data. It syncs Google Health, summarizes recent exercise records, loads health goals/memory, applies a curated evidence pack, and stores the resulting recommendation/memory candidates.

Example:

```bash
python3 /home/node/.openclaw/workspace/skills/health-coach/scripts/health_coach.py \
  --period-days 7 \
  --question "Review my health this week and tell me what to improve next."
```

See [docs/google-health-coach.md](docs/google-health-coach.md).
