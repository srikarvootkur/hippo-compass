# Adding A New Skill

This is the workflow for building new Hippo Compass skills. It is written for me, for Codex/coding agents working in this repo, and for other people setting up their own version.

The default pattern is:

```text
OpenClaw skill -> assistant-api -> LangGraph/workflow/service -> Postgres/memory/connectors
```

OpenClaw should be the assistant shell. It should not own durable memory, OAuth tokens, bank credentials, health tokens, or database access.

## 1. Decide What Kind Of Skill This Is

Use a thin OpenClaw skill only when the action can safely be expressed as a command that calls Hippo Compass.

Use an `assistant-api` endpoint when the skill needs:

- memory reads or writes
- imported app data
- OAuth tokens or other credentials
- approvals, audit logs, or recommendations
- background jobs, retries, or scheduled workflows
- anything that should still work if OpenClaw is replaced later

Use LangGraph when the workflow is multi-step, stateful, retryable, or approval-heavy.

Use the OpenAI Agents SDK service when a focused specialist agent is helpful, such as health coaching, nutrition review, writing-style drafting, or research-backed summaries.

## 2. Define The Contract First

Before writing the OpenClaw skill, define the backend API shape.

Minimum contract:

- endpoint path
- request JSON
- response JSON
- auth header
- side effects
- safety rules
- test data

Example:

```text
POST /workflows/google-health/coach-review
Auth: X-Assistant-API-Key
Input: period_days, question, force_sync, goals
Output: summary, patterns, next_actions, citations, created_recommendation_id
Side effects: sync source records, create recommendation, write memory candidates
```

## 3. Build The Backend First

If the skill calls real data or memory, implement the backend before the OpenClaw wrapper.

Checklist:

- add/extend `assistant-api`
- add/extend LangGraph workflow if needed
- add/extend specialist service if needed
- write raw source records before normalized summaries
- keep secrets in `.env` or Postgres, never git
- add tests with mocked external APIs
- run the endpoint directly with `curl`

The skill is not done until the backend can be called without OpenClaw.

## 4. Create The Skill Folder

Copy the template:

```bash
cp -R templates/openclaw-skill skills/my-new-skill
```

Rename files and edit:

```text
skills/my-new-skill/
  SKILL.md
  scripts/my_new_skill.py
  tests/test_my_new_skill_script.py
```

Every OpenClaw-discoverable skill needs YAML frontmatter:

```yaml
---
name: my-new-skill
description: "Use when the user wants ..."
metadata:
  {
    "openclaw":
      {
        "requires": { "bins": ["python3"] },
      },
  }
---
```

The description matters because the agent uses it to decide when the skill should appear.

## 5. Keep The Skill Thin

A good Hippo Compass OpenClaw skill usually does only this:

1. Parse command arguments.
2. Read `HIPPO_COMPASS_API_URL`.
3. Read `HIPPO_COMPASS_API_KEY`.
4. Call one `assistant-api` endpoint.
5. Print JSON or a concise human-readable result.
6. Return non-zero on API errors.

Do not put OAuth tokens, app passwords, bank keys, or raw database access in the skill.

## 6. Test Locally

Run script tests:

```bash
pytest skills/my-new-skill/tests
```

Run the script against the local backend:

```bash
HIPPO_COMPASS_API_URL=http://localhost:8080 HIPPO_COMPASS_API_KEY=change-me-local-dev python3 skills/my-new-skill/scripts/my_new_skill.py --input "example"
```

If the skill has sensitive data, use mock payloads for tests and keep real values out of fixtures.

## 7. Install On OpenClaw

On the VPS:

```bash
cd ~/hippo-compass
git pull
mkdir -p /root/.openclaw/workspace/skills
cp -R skills/my-new-skill /root/.openclaw/workspace/skills/
chown -R 1000:1000 /root/.openclaw/workspace/skills/my-new-skill
chmod -R a+rX /root/.openclaw/workspace/skills/my-new-skill
```

Register it with the main OpenClaw agent:

```bash
cd /opt/openclaw
docker compose -f /opt/openclaw/docker-compose.yml run --rm openclaw-cli skills install /home/node/.openclaw/workspace/skills/my-new-skill --as my-new-skill --force --agent main
docker compose -f /opt/openclaw/docker-compose.yml run --rm openclaw-cli skills check --agent main
docker compose -f /opt/openclaw/docker-compose.yml restart openclaw-gateway
```

Make sure `/opt/openclaw/.env` has:

```text
HIPPO_COMPASS_API_URL=http://assistant-api:8080
HIPPO_COMPASS_API_KEY=your-secret
```

## 8. Smoke Test From The Container

First confirm container networking:

```bash
cd /opt/openclaw
docker compose -f /opt/openclaw/docker-compose.yml exec openclaw-gateway sh -lc 'getent hosts assistant-api && curl http://assistant-api:8080/health'
```

Then run the skill script from the same container:

```bash
docker compose -f /opt/openclaw/docker-compose.yml exec openclaw-gateway sh -lc 'python3 /home/node/.openclaw/workspace/skills/my-new-skill/scripts/my_new_skill.py --input "example"'
```

If this works, the skill itself is probably fine.

## 9. Test OpenClaw And Telegram

Use the CLI before Telegram:

```bash
cd /opt/openclaw
docker compose -f /opt/openclaw/docker-compose.yml run --rm openclaw-cli agent --agent main --message "Use my-new-skill to ..." --json
```

Then send a fresh Telegram message.

If Telegram says the skill is missing but `skills check` shows it, the Telegram session may have a stale skill snapshot. Start a new chat/session if OpenClaw supports it. If needed, back up and remove only that stale session from:

```text
/root/.openclaw/agents/main/sessions/sessions.json
```

Do not delete all sessions casually. Back up first.

## 10. Commit The Skill

Before pushing:

```bash
git status
pytest skills/my-new-skill/tests
git add skills/my-new-skill runbooks docs README.md
git commit -m "Add my new skill"
git push
```

Never commit `.env`, OAuth tokens, Telegram tokens, SSH keys, Google secrets, bank credentials, database dumps, or real private health payloads.

## Good Skill Design Rules

- One skill should map to one user-facing capability.
- The skill should call Hippo Compass, not external providers directly, unless it is clearly public/non-sensitive.
- Durable memory belongs in Postgres.
- Credentials belong in `.env` or encrypted storage, not OpenClaw skill files.
- Scripts should have tests.
- The backend endpoint should be usable by future agents, not just OpenClaw.
- Every skill should have one direct smoke-test command.
- Every sensitive or external-write action should go through approvals.
