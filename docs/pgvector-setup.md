# pgvector Setup

Hippo Compass uses Postgres with `pgvector` as the durable memory layer.

The LLM should not be treated as the memory store. The database is the source of truth.

## Managed Database Recommendation

Use Supabase or Neon for v1.

Reasons:

- lower operational burden
- backups are easier
- database is separate from the VPS
- easier to move the app later

## Enable pgvector

In your database SQL editor:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Then run:

```sql
-- paste db/migrations/001_initial.sql here
```

## Production Environment

Set:

```text
DATABASE_URL=postgresql://...
```

Use the provider's recommended pooled connection string if they provide one.

## Local Development

The Docker Compose file includes a local pgvector Postgres container behind the `local-db` profile:

```bash
docker compose -f infra/docker-compose.yml --env-file .env --profile local-db up --build
```

For local dev, this default works:

```text
DATABASE_URL=postgresql://assistant:assistant@postgres:5432/assistant
```

## Memory Tables

The initial migration creates:

- `source_connections`
- `source_records`
- `memories`
- `goals`
- `journal_entries`
- `approvals`
- `audit_logs`

Vector search will be layered onto `memories.embedding` and `journal_entries.embedding` after the first embedding pipeline is added.
