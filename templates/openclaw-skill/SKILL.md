---
name: my-new-skill
description: "Use when the user wants this Hippo Compass capability."
metadata:
  {
    "openclaw":
      {
        "requires": { "bins": ["python3"] },
      },
  }
---

# My New Skill

Use this skill when the user asks for the capability described in the frontmatter.

## Inputs

- `input`: describe the main user input.

## Environment

- `HIPPO_COMPASS_API_URL`
- `HIPPO_COMPASS_API_KEY`

## Behavior

1. Call the matching Hippo Compass `assistant-api` endpoint.
2. Return the result clearly.
3. Do not store secrets or durable memory in OpenClaw.
4. For sensitive actions, return an approval request instead of taking action directly.

## Script

```bash
python3 scripts/my_new_skill.py --input "example"
```
