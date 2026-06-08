# Google Health Coach

The Google Health Coach workflow turns imported Google Health exercise records into a wellness coaching review that OpenClaw can use.

## Architecture

- OpenClaw calls `skills/health-coach`.
- The skill calls `assistant-api` at `/workflows/google-health/coach-review`.
- `assistant-api` syncs Google Health, aggregates recent exercise records, loads health memories and active health goals, then calls LangGraph.
- LangGraph attaches a curated evidence pack and calls the specialist service.
- The specialist returns summary, patterns, evidence-based guidance, next actions, questions, citations, memory candidates, and a safety level.
- `assistant-api` stores the recommendation and memory candidates in Postgres.

OpenClaw does not store Google OAuth credentials, read Postgres directly, or reason over raw records by itself.

## API

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-Assistant-API-Key: YOUR_ASSISTANT_API_KEY" \
  -d '{"period_days":7,"force_sync":true,"question":"Review my health this week and tell me what to improve next.","goals":{}}' \
  http://localhost:8080/workflows/google-health/coach-review
```

Response shape:

```json
{
  "workflow": "google_health_coach_review",
  "period_days": 7,
  "data_sources": ["google_health"],
  "summary": "...",
  "patterns": ["..."],
  "evidence_based_guidance": ["..."],
  "next_actions": ["..."],
  "questions_for_user": ["..."],
  "citations": [{"title": "...", "url": "..."}],
  "created_recommendation_id": "...",
  "created_memory_ids": []
}
```

## OpenClaw Skill

```bash
HIPPO_COMPASS_API_URL=http://assistant-api:8080 HIPPO_COMPASS_API_KEY=YOUR_ASSISTANT_API_KEY python3 /home/node/.openclaw/workspace/skills/health-coach/scripts/health_coach.py --period-days 7 --question "Review my health this week."
```

Useful prompts:

- "Review my health this week and tell me what to improve next."
- "What should I do tomorrow based on my workouts?"
- "Summarize my recent Google Health activity."
- "Am I being consistent enough with exercise?"

## Evidence Pack

The v1 coach uses a curated evidence pack:

- CDC Adult Activity Guidelines: <https://www.cdc.gov/physical-activity-basics/guidelines/adults.html>
- American Heart Association Physical Activity Recommendations: <https://www.heart.org/en/healthy-living/fitness/fitness-basics/aha-recs-for-physical-activity-in-adults>
- Google Health API codelab: <https://developers.google.com/health/codelabs/make-your-first-api-call>
- Google Fitbit Personal Health Coach preview: <https://blog.google/products/fitbit/fitbit-ai-personal-health-coach-preview>
- Google Research Health AI: <https://research.google/research-areas/health-ai/>

Live research should be added later as an explicit tool path, not silently mixed into every review.

## Safety

This is a wellness coach, not medical advice.

- It can discuss activity consistency, recovery, sleep hygiene, training balance, and habit formation.
- It should not diagnose symptoms.
- It should not recommend medication changes.
- It should route chest pain, fainting, urgent symptoms, medication questions, and diagnosis requests to a qualified clinician.
