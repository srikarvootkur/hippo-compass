# Skills

These are OpenClaw workspace skills that expose Hippo Compass capabilities.

The pattern is intentionally boring:

```text
skill script -> assistant-api -> workflow/service -> memory/connectors
```

Skills should be thin adapters. They should not store credentials, own long-term memory, or talk directly to Postgres.

## Current Skills

- `search-memory`: search durable Hippo Compass memories.
- `save-journal-entry`: save a journal/reflection entry.
- `review-recommendations`: review pending assistant recommendations.
- `health-coach`: review Google Health/Fitbit activity through the health coach workflow.

## Creating A Skill

Use [../runbooks/adding-new-skill.md](../runbooks/adding-new-skill.md).

For a starter folder, copy:

```bash
cp -R templates/openclaw-skill skills/my-new-skill
```

Every skill that OpenClaw should discover needs YAML frontmatter in `SKILL.md`:

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

After copying to the OpenClaw workspace, install it:

```bash
cd /opt/openclaw
docker compose -f /opt/openclaw/docker-compose.yml run --rm openclaw-cli skills install /home/node/.openclaw/workspace/skills/my-new-skill --as my-new-skill --force --agent main
docker compose -f /opt/openclaw/docker-compose.yml run --rm openclaw-cli skills check --agent main
docker compose -f /opt/openclaw/docker-compose.yml restart openclaw-gateway
```
