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
db/migrations/         Postgres and pgvector schema
prompts/               Starting prompts
runbooks/              Ops notes and future migration guides
```

## Quick Local Setup

This gets the services running locally with mock workflows.

1. Install Docker Desktop.

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
3. Point DNS records at the server:

   ```text
   assistant.yourdomain.com -> server IPv4
   openclaw.yourdomain.com  -> server IPv4
   ```

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

9. Start production services:

   ```bash
   docker compose -f infra/docker-compose.yml --env-file .env --profile production --profile openclaw up -d --build
   ```

10. Check status:

   ```bash
   docker compose -f infra/docker-compose.yml --env-file .env ps
   curl https://assistant.yourdomain.com/health
   ```

## Connecting OpenClaw

OpenClaw should call the assistant API as a tool server.

Minimum endpoints:

- `POST /memory/search`
- `POST /memory/write`
- `POST /journal_entries`
- `GET /recommendations`
- `POST /recommendations`
- `POST /approvals`
- `POST /tool_runs`
- `POST /workflows/cronometer/daily-review`

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
