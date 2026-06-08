---
name: save-journal-entry
description: "Save a journal entry, reflection, voice transcript, or life note into durable Hippo Compass memory."
metadata:
  {
    "openclaw":
      {
        "requires": { "bins": ["python3"] },
      },
  }
---

# Save Hippo Compass Journal Entry

Use this skill when the user wants to save a journal entry, reflection, voice transcript, or life note into durable memory.

## Inputs

- `source`: where the entry came from, such as `manual`, `voice`, or `import`.
- `content`: journal text or transcript.
- `title`: optional short title.

## Environment

- `HIPPO_COMPASS_API_URL`
- `HIPPO_COMPASS_API_KEY`

## Behavior

1. Call `/journal_entries`.
2. Store the journal entry.
3. Let the API create an initial memory candidate and review recommendation.
4. Return the saved entry ID.

## Safety

- Do not publish or expose private journal content.
- Do not turn journal themes into external actions.

## Script

```bash
python3 scripts/save_journal_entry.py --source manual --content "Example journal text"
```
