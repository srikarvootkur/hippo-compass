# Hippo Compass Health Coach

Use this skill when the user asks for a Google Health/Fitbit activity review, wellness coaching, workout consistency advice, or a summary of recent health data.

## Inputs

- `question`: natural language health coaching question.
- `period_days`: number of days to review, default `7`.
- `force_sync`: whether Hippo Compass should sync Google Health before reviewing, default `true`.

## Environment

- `HIPPO_COMPASS_API_URL`
- `HIPPO_COMPASS_API_KEY`

## Behavior

1. Call `/workflows/google-health/coach-review`.
2. Let Hippo Compass sync Google Health and load memory/goals.
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
