# Search Hippo Compass Memory

Use this skill when the user asks what Hippo Compass remembers, wants context loaded, or wants prior themes searched.

## Inputs

- `query`: search terms or natural language question.
- `limit`: optional result count.

## Environment

- `HIPPO_COMPASS_API_URL`
- `HIPPO_COMPASS_API_KEY`

## Behavior

1. Query Hippo Compass through `/memory/search`.
2. Return concise matching memories.
3. Clearly distinguish retrieved memory from fresh inference.

## Safety

- Do not claim a memory exists unless the API returned it.
- Do not expose private memories in public demos.
- Do not update memories from this skill.

## Script

```bash
python3 scripts/search_memory.py --query "sleep phone"
```
