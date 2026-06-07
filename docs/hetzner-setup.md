# Hetzner Setup

This is the first VPS path for Hippo Compass.

The goal is to get a simple server running Docker Compose, prove the backend works, and then add DNS/Caddy/OpenClaw once the core services are healthy.

## 1. Create The Server

In Hetzner Cloud:

1. Create a new project.
2. Add an SSH key.
   - Paste the public key, usually `~/.ssh/id_ed25519.pub`.
   - Do not paste the private key that starts with `-----BEGIN OPENSSH PRIVATE KEY-----`.
3. Create a server:
   - Image: Ubuntu LTS.
   - Type: CPX11 is okay to start; CPX21 is more comfortable.
   - Architecture: x86.
   - Networking: keep public IPv4 on. IPv6 can stay on. Private networking is not needed for v1.
   - Volumes: skip for v1.

After the server is created, copy its public IPv4 address.

## 2. Optional DNS

You do not need a domain to start building.

If you already own a domain and want HTTPS now, create DNS records wherever your domain is managed:

```text
assistant.yourdomain.com A YOUR_SERVER_IP
openclaw.yourdomain.com  A YOUR_SERVER_IP
```

If you do not own a domain yet, skip this step. Hetzner DNS zones manage records for domains you already own; they do not register/buy a domain for you.

## 3. SSH Into The Server

```bash
ssh root@YOUR_SERVER_IP
```

If the server says a restart is required after updates, run:

```bash
reboot
```

Wait about 30 seconds and SSH back in.

## 4. Install Base Packages

```bash
apt update
apt upgrade -y
apt install -y ca-certificates curl git ufw nano
```

If using a 2 GB RAM server, add swap:

```bash
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
free -h
```

## 5. Install Docker Engine

Docker Desktop is not needed on Hetzner/Linux.

```bash
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Check:

```bash
docker --version
docker compose version
```

## 6. Set Up Firewall

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status
```

Hippo Compass binds backend ports to `127.0.0.1`, so they are only reachable from the VPS itself unless you use Caddy or an SSH tunnel.

## 7. Clone Hippo Compass

Public repo:

```bash
git clone https://github.com/srikarvootkur/hippo-compass.git
cd hippo-compass
cp infra/env.example .env
```

Private repo:

- Best long-term option: add a GitHub deploy key for this VPS.
- Quick setup option: use a fine-grained GitHub token with only `Contents: Read-only` for this repo.

Example with a token:

```bash
git clone https://srikarvootkur:YOUR_GITHUB_TOKEN@github.com/srikarvootkur/hippo-compass.git
cd hippo-compass
git remote set-url origin https://github.com/srikarvootkur/hippo-compass.git
cp infra/env.example .env
```

Do not commit GitHub tokens, SSH keys, `.env`, database URLs, or API keys.

If `git pull` asks for a GitHub password, use a fine-grained token instead of your account password. GitHub no longer supports password authentication for git over HTTPS.

If `git pull` says local files would be overwritten, check the changed files before pulling:

```bash
git status
git diff
```

For local-only VPS changes that you do not need, stash them:

```bash
git stash push -m "local VPS changes before pull"
git pull
```

## 8. Configure Environment

Generate an assistant API key:

```bash
openssl rand -hex 32
```

Edit:

```bash
nano .env
```

Minimum values for first backend test:

```text
ASSISTANT_API_KEY=paste-random-value-here
DATABASE_URL=postgresql://assistant:assistant@postgres:5432/assistant
OPENAI_API_KEY=
```

Leave `OPENAI_API_KEY` empty for mock workflows. Add it later for real OpenAI calls.

If you already have DNS, also set:

```text
ASSISTANT_DOMAIN=assistant.yourdomain.com
OPENCLAW_DOMAIN=openclaw.yourdomain.com
```

Save in nano with `Ctrl + O`, `Enter`, then `Ctrl + X`.

In nano, undo is usually `Alt + U` on Linux terminals. If your keyboard sends the wrong key, press `Esc`, then `U`.

## 9. Start Backend Services

For first setup with local Postgres:

```bash
docker compose -f infra/docker-compose.yml --env-file .env --profile local-db up -d --build
```

If using managed Postgres, set `DATABASE_URL` to the managed database URL and omit `--profile local-db`:

```bash
docker compose -f infra/docker-compose.yml --env-file .env up -d --build
```

## 10. Verify Backend Health

```bash
docker compose -f infra/docker-compose.yml --env-file .env ps
curl http://localhost:8080/health
curl http://localhost:8070/health
curl http://localhost:8090/health
```

Try the mock Cronometer workflow:

```bash
curl -X POST http://localhost:8080/workflows/cronometer/daily-review \
  -H "Content-Type: application/json" \
  -H "X-Assistant-API-Key: YOUR_ASSISTANT_API_KEY" \
  -d '{"use_mock_data": true}'
```

The mock data comes from `services/agents-workflows/app/main.py`. It is fake fixture data used to prove the workflow works before a real Cronometer connector exists.

## 11. Access From Your Mac Without DNS

Open an SSH tunnel from your Mac:

```bash
ssh -L 8080:localhost:8080 -L 8070:localhost:8070 -L 8090:localhost:8090 root@YOUR_SERVER_IP
```

Leave that terminal open. In another Mac terminal:

```bash
curl http://localhost:8080/health
```

## 12. Optional DNS + Caddy

Do this when you want public HTTPS URLs, mobile/webhook access, or OAuth callbacks.

1. Point DNS:

   ```text
   assistant.yourdomain.com A YOUR_SERVER_IP
   openclaw.yourdomain.com  A YOUR_SERVER_IP
   ```

2. Set domains in `.env`.

3. Start Caddy:

   ```bash
   docker compose -f infra/docker-compose.yml --env-file .env --profile local-db --profile production up -d --build
   ```

4. Verify:

   ```bash
   curl https://assistant.yourdomain.com/health
   ```

If using managed Postgres, omit `--profile local-db`.

## 13. OpenClaw

Install/configure OpenClaw after the Hippo Compass backend is healthy.

From the OpenClaw repo root, use the current Docker setup script:

```bash
./scripts/docker/setup.sh
```

If `./docker-setup.sh` is mentioned somewhere older, ignore it; that path may not exist.

During onboarding, keep the first pass simple:

- Channel: Telegram is fine if you already have a bot token. Otherwise skip.
- Provider: OpenAI.
- Search provider: DuckDuckGo or skip.
- Skills: skip for now.
- Hooks: skip for now.

Access the OpenClaw dashboard through an SSH tunnel:

```bash
ssh -L 18789:localhost:18789 root@YOUR_SERVER_IP
```

Then open:

```text
http://127.0.0.1:18789
```

OpenClaw should call:

```text
HIPPO_COMPASS_API_URL=http://assistant-api:8080
HIPPO_COMPASS_API_KEY=YOUR_ASSISTANT_API_KEY
```

If you set up DNS/Caddy, use:

```text
HIPPO_COMPASS_API_URL=https://assistant.yourdomain.com
HIPPO_COMPASS_API_KEY=YOUR_ASSISTANT_API_KEY
```

OpenClaw should call `assistant-api`, not `langgraph-workflows` or `agents-workflows` directly.

Because OpenClaw and Hippo Compass run in separate Docker Compose projects, connect them with a shared Docker network:

```bash
docker network create hippo-compass-net
docker network connect --alias assistant-api hippo-compass-net infra-assistant-api-1
docker network connect hippo-compass-net openclaw-openclaw-gateway-1
```

Then confirm from inside the OpenClaw container:

```bash
cd /opt/openclaw
docker compose -f /opt/openclaw/docker-compose.yml exec openclaw-gateway sh
curl http://assistant-api:8080/health
```

Copy Hippo Compass skills into the OpenClaw workspace:

```bash
mkdir -p /root/.openclaw/workspace/skills
cp -R ~/hippo-compass/skills/search-memory /root/.openclaw/workspace/skills/
cp -R ~/hippo-compass/skills/save-journal-entry /root/.openclaw/workspace/skills/
cp -R ~/hippo-compass/skills/review-recommendations /root/.openclaw/workspace/skills/
chmod -R a+rX /root/.openclaw/workspace/skills
```

Inside the OpenClaw container, use `/home/node/.openclaw/workspace`, not `/root/.openclaw/workspace`.

Test:

```bash
HIPPO_COMPASS_API_URL=http://assistant-api:8080 HIPPO_COMPASS_API_KEY=YOUR_ASSISTANT_API_KEY python3 /home/node/.openclaw/workspace/skills/search-memory/scripts/search_memory.py --query test
```

If Telegram fails with a `gpt-5.3-codex` model error, switch to a regular OpenAI model and restart:

```bash
cd /opt/openclaw
docker compose -f /opt/openclaw/docker-compose.yml run --rm openclaw-cli config set agents.defaults.model.primary openai/gpt-5.4-mini
docker compose -f /opt/openclaw/docker-compose.yml restart openclaw-gateway
```

The gateway runs on the VPS. Your Mac browser and SSH tunnel can be closed when you are not using the Control UI.

If a command works on the VPS host but not inside the OpenClaw container, remember that the container has a different filesystem and network view:

- host OpenClaw workspace: `/root/.openclaw/workspace`
- container OpenClaw workspace: `/home/node/.openclaw/workspace`
- host `localhost:8080`: Hippo Compass API on the VPS
- container `localhost:8080`: inside the OpenClaw container, usually wrong
- container API URL after shared network setup: `http://assistant-api:8080`

Do not run host-level `docker compose` commands from inside the OpenClaw container unless you intentionally installed/mounted Docker there. Exit back to the VPS shell first.

## 14. Google Health Connector

After the backend is healthy, follow [google-health-connector.md](google-health-connector.md) to connect Google/Fitbit activity data.

For no-DNS setup, keep an SSH tunnel open from your Mac:

```bash
ssh -L 8080:localhost:8080 root@YOUR_SERVER_IP
```

Then start OAuth from your Mac:

```bash
curl -H "X-Assistant-API-Key: YOUR_ASSISTANT_API_KEY" \
  http://localhost:8080/connectors/google-health/oauth/start
```

After consent, verify and sync:

```bash
curl -H "X-Assistant-API-Key: YOUR_ASSISTANT_API_KEY" \
  http://localhost:8080/connectors/google-health/status

curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-Assistant-API-Key: YOUR_ASSISTANT_API_KEY" \
  -d '{"data_type":"exercise"}' \
  http://localhost:8080/connectors/google-health/sync
```

## Maintenance Commands

Update code:

```bash
git pull
docker compose -f infra/docker-compose.yml --env-file .env --profile local-db up -d --build
```

View logs:

```bash
docker compose -f infra/docker-compose.yml --env-file .env logs -f assistant-api
```

Restart:

```bash
docker compose -f infra/docker-compose.yml --env-file .env restart
```
