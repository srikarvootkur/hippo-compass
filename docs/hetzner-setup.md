# Hetzner Setup

This is the first production path for Hippo Compass.

The goal is not to build a perfect cloud platform on day one. The goal is to get a simple VPS running Docker Compose, connect it to managed Postgres, and keep the architecture easy to move later.

## 1. Create The Server

In Hetzner Cloud:

1. Create a new project.
2. Add an SSH key.
3. Create a server:
   - Image: Ubuntu LTS
   - Type: start with 2-4 GB RAM
   - Location: closest reasonable region
   - Networking: public IPv4 is enough for v1

After the server is created, copy its IP address.

## 2. Point DNS

Create DNS records wherever your domain is hosted:

```text
assistant.yourdomain.com A YOUR_SERVER_IP
openclaw.yourdomain.com  A YOUR_SERVER_IP
```

Wait for DNS to resolve before expecting HTTPS to work.

## 3. SSH Into The Server

```bash
ssh root@YOUR_SERVER_IP
```

## 4. Install Base Packages

```bash
apt update
apt install -y ca-certificates curl git ufw nano
```

## 5. Install Docker

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

## 7. Clone Hippo Compass

```bash
git clone https://github.com/srikarvootkur/hippo-compass.git
cd hippo-compass
cp infra/env.example .env
```

## 8. Configure Environment

Edit:

```bash
nano .env
```

Minimum production values:

```text
ASSISTANT_DOMAIN=assistant.yourdomain.com
OPENCLAW_DOMAIN=openclaw.yourdomain.com
ASSISTANT_API_KEY=a-long-random-secret
DATABASE_URL=your-managed-postgres-url
OPENAI_API_KEY=your-openai-api-key
```

Generate a local secret if needed:

```bash
openssl rand -hex 32
```

Do not commit `.env`.

## 9. Set Up Managed Postgres

Use Supabase or Neon for v1.

In the SQL editor, run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Then run the SQL from:

```text
db/migrations/001_initial.sql
```

Copy the database connection string into `DATABASE_URL`.

## 10. Start Production Services

```bash
docker compose -f infra/docker-compose.yml --env-file .env --profile production --profile openclaw up -d --build
```

Check:

```bash
docker compose -f infra/docker-compose.yml --env-file .env ps
docker compose -f infra/docker-compose.yml --env-file .env logs --tail=100 assistant-api
```

## 11. Verify Health

```bash
curl https://assistant.yourdomain.com/health
```

If DNS is not ready yet, test locally on the server:

```bash
curl http://localhost:8080/health
curl http://localhost:8070/health
curl http://localhost:8090/health
```

## 12. Try A Workflow

```bash
curl -X POST https://assistant.yourdomain.com/workflows/cronometer/daily-review \
  -H "Content-Type: application/json" \
  -H "X-Assistant-API-Key: your-secret" \
  -d '{"use_mock_data": true}'
```

## 13. Connect OpenClaw

Configure OpenClaw to call the assistant API as a tool server.

Use:

```text
Base URL: https://assistant.yourdomain.com
Header: X-Assistant-API-Key: your-secret
```

Start with:

- `/memory/search`
- `/memory/write`
- `/approvals`
- `/workflows/cronometer/daily-review`

## Maintenance Commands

Update code:

```bash
git pull
docker compose -f infra/docker-compose.yml --env-file .env --profile production --profile openclaw up -d --build
```

View logs:

```bash
docker compose -f infra/docker-compose.yml --env-file .env logs -f assistant-api
```

Restart:

```bash
docker compose -f infra/docker-compose.yml --env-file .env restart
```
