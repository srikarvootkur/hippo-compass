---
name: health-coach
description: "Review Google Health/Fitbit, Hevy, Cronometer, and typed Hippo Compass health data for wellness coaching, recovery, nutrition, strength, activity, and next actions."
metadata:
  {
    "openclaw":
      {
        "requires": { "bins": ["python3"] },
      },
  }
---

# Hippo Compass Health Coach

Use this skill when the user asks for a health data review, Google Health/Fitbit review, sleep/recovery summary, strength training review, nutrition pattern review, workout consistency advice, or next health actions.

## Inputs

- `question`: natural language health coaching question.
- `period_days`: number of days to review, default `7`.
- `force_sync`: whether Hippo Compass should sync Google Health before reviewing, default `true`.

## Environment

- `HIPPO_COMPASS_API_URL`
- `HIPPO_COMPASS_API_KEY`

## Behavior

1. Call `/workflows/health/coach-review`.
2. Let Hippo Compass sync Google Health, load typed health summaries, and load memory/goals.
3. Return the summary, patterns, next actions, and citations.
4. Clearly treat the output as wellness coaching, not medical diagnosis.

## Safety

- Do not diagnose symptoms.
- Do not recommend medication changes.
- Do not treat emergency or urgent symptoms as a chat problem.
- For medical concerns, tell the user to contact a qualified clinician.

## Script

```bash
python3 scripts/health_coach.py --period-days 7 --question "Review my health this week and tell me what to improve next."
```

On the Hetzner OpenClaw gateway, use:

```bash
HIPPO_COMPASS_API_URL=http://assistant-api:8080 HIPPO_COMPASS_API_KEY=$HIPPO_COMPASS_API_KEY python3 /home/node/.openclaw/workspace/skills/health-coach/scripts/health_coach.py --period-days 7 --question "Review my health this week and tell me what to improve next."
```
