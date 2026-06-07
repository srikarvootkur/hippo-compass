# OpenClaw Setup

OpenClaw is the first agent shell. Configure it to call `assistant-api` endpoints as tools.

Set up the Hippo Compass backend first. OpenClaw is the shell; `assistant-api`, LangGraph, and Postgres are the memory/workflow layer it should call.

Minimum tool endpoints:

- `POST /memory/search`
- `POST /memory/write`
- `POST /journal_entries`
- `GET /recommendations`
- `POST /recommendations`
- `POST /approvals`
- `POST /tool_runs`
- `POST /workflows/cronometer/daily-review`

OpenClaw should authenticate with `X-Assistant-API-Key`.

Do not put durable memory or integration secrets directly inside OpenClaw configuration when those can live behind `assistant-api`.

OpenClaw should call `assistant-api`, not `langgraph-workflows` or `agents-workflows` directly. That keeps the workflow internals replaceable.

## Docker Install

From the OpenClaw repo root, the current Docker setup script is:

```bash
./scripts/docker/setup.sh
```

The older `./docker-setup.sh` path may not exist.

For a VPS, keep the OpenClaw gateway private at first and access it with an SSH tunnel:

```bash
ssh -L 18789:localhost:18789 root@YOUR_SERVER_IP
```

Then open:

```text
http://127.0.0.1:18789
```

Do not expose the OpenClaw gateway publicly until you have DNS, HTTPS, and auth configured.

## Onboarding Choices

Recommended first-run choices:

- **Channel:** Telegram is fine if you already have a bot token. Otherwise skip and add it later.
- **Telegram:** optional. Create a bot with `@BotFather` later and keep the token out of git.
- **Provider:** choose OpenAI for the first setup.
- **Search provider:** choose DuckDuckGo if you want the easiest no-key option, or skip search for now.
- **Skills:** skip during first setup. Add Hippo Compass skills after the dashboard and provider work.
- **Hooks:** skip during first setup. Add hooks later for guardrails, audit flows, or approval checkpoints.

The first milestone is:

```text
OpenClaw boots
Control UI opens through SSH tunnel
Provider works
Hippo Compass backend is reachable
```

## Model Fix

If Telegram or the Control UI fails with an error like:

```text
'gpt-5.3-codex' model is not supported when using Codex with a ChatGPT account
```

switch OpenClaw to a regular OpenAI API model:

```bash
cd /opt/openclaw
docker compose -f /opt/openclaw/docker-compose.yml run --rm openclaw-cli config set agents.defaults.model.primary openai/gpt-5.4-mini
docker compose -f /opt/openclaw/docker-compose.yml restart openclaw-gateway
```

If that model is not available in your account, pick another OpenAI model shown by OpenClaw.

## Telegram Check

If Telegram does not respond, first watch gateway logs:

```bash
cd /opt/openclaw
docker compose -f /opt/openclaw/docker-compose.yml logs -f openclaw-gateway
```

Send `/start` and then `hello` to the bot. If the logs show model errors, fix the model before reconfiguring Telegram.

If OpenClaw gives a pairing code, approve it inside the OpenClaw container or CLI:

```bash
openclaw pairing approve telegram YOUR_CODE
```

## Workspace Skills

This repo includes starter OpenClaw-style workspace skills:

- `skills/search-memory`
- `skills/save-journal-entry`
- `skills/review-recommendations`

Configure their environment with:

```text
HIPPO_COMPASS_API_URL=http://assistant-api:8080
HIPPO_COMPASS_API_KEY=your-secret
```

If DNS/Caddy is configured, use:

```text
HIPPO_COMPASS_API_URL=https://assistant.yourdomain.com
HIPPO_COMPASS_API_KEY=your-secret
```

OpenClaw runs in a separate Docker Compose project, so `localhost` inside OpenClaw means the OpenClaw container, not the VPS host. The working no-DNS setup is a shared Docker network.

Create/connect the network from the VPS host:

```bash
docker network create hippo-compass-net
docker network connect --alias assistant-api hippo-compass-net infra-assistant-api-1
docker network connect hippo-compass-net openclaw-openclaw-gateway-1
```

If a command says the network or endpoint already exists, that is fine.

Confirm from inside the OpenClaw container:

```bash
cd /opt/openclaw
docker compose -f /opt/openclaw/docker-compose.yml exec openclaw-gateway sh
curl http://assistant-api:8080/health
```

Expected result:

```json
{"service":"personal-assistant-api","status":"ok"}
```

Copy the starter skills into the OpenClaw workspace from the VPS host:

```bash
mkdir -p /root/.openclaw/workspace/skills
cp -R ~/hippo-compass/skills/search-memory /root/.openclaw/workspace/skills/
cp -R ~/hippo-compass/skills/save-journal-entry /root/.openclaw/workspace/skills/
cp -R ~/hippo-compass/skills/review-recommendations /root/.openclaw/workspace/skills/
chmod -R a+rX /root/.openclaw/workspace/skills
```

Inside the OpenClaw container, the workspace path is:

```text
/home/node/.openclaw/workspace
```

Test a skill from inside the OpenClaw container:

```bash
HIPPO_COMPASS_API_URL=http://assistant-api:8080 HIPPO_COMPASS_API_KEY=your-secret python3 /home/node/.openclaw/workspace/skills/search-memory/scripts/search_memory.py --query test
```

Empty results are fine:

```json
{"query":"test","results":[]}
```

Save and search a first journal entry:

```bash
HIPPO_COMPASS_API_URL=http://assistant-api:8080 HIPPO_COMPASS_API_KEY=your-secret python3 /home/node/.openclaw/workspace/skills/save-journal-entry/scripts/save_journal_entry.py --source manual --content "I got Hippo Compass and OpenClaw connected today."
HIPPO_COMPASS_API_URL=http://assistant-api:8080 HIPPO_COMPASS_API_KEY=your-secret python3 /home/node/.openclaw/workspace/skills/search-memory/scripts/search_memory.py --query "OpenClaw connected"
```

Manual `docker network connect` changes may need to be repeated if containers are recreated. Make this persistent later with Compose network configuration or DNS/Caddy.

## Runtime Notes

The OpenClaw gateway runs on the VPS. Your Mac, Chrome tab, and SSH tunnel do not need to stay open for Telegram/OpenClaw to keep running.

The SSH tunnel is only for opening the private Control UI from your Mac:

```bash
ssh -L 18789:localhost:18789 root@YOUR_SERVER_IP
```

Check gateway status:

```bash
cd /opt/openclaw
docker compose -f /opt/openclaw/docker-compose.yml ps
```

## Why This Boundary Exists

OpenClaw is the first shell, not the permanent source of truth.

If another agent framework replaces OpenClaw later, it should call the same `assistant-api` endpoints and use the same Postgres memory. That is the whole portability bet.
