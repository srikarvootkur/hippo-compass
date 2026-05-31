# Cloud Migration

The v1 target is Hetzner compute plus managed Postgres.

To move later:

1. Deploy the same Docker Compose services or equivalent containers.
2. Point `DATABASE_URL` at the existing managed Postgres or restore a backup.
3. Move DNS.
4. Verify health checks and workflow endpoints.
5. Keep OpenClaw and alternate agents behind the same `assistant-api`.
