# Review Hippo Compass Recommendations

Use this skill when the user wants to inspect assistant-generated recommendations.

## Inputs

- `status`: recommendation status to list, usually `pending`.
- `limit`: optional number of recommendations.

## Environment

- `HIPPO_COMPASS_API_URL`
- `HIPPO_COMPASS_API_KEY`

## Behavior

1. List pending recommendations through `/recommendations`.
2. Do not execute external actions directly.
3. Treat recommendations as suggestions until an approval/action workflow handles them.

## Script

```bash
python3 scripts/review_recommendations.py --status pending
```
