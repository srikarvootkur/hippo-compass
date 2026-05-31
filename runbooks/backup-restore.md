# Backup And Restore

## Managed Postgres

Use provider backups for primary recovery. Also schedule logical exports for portability.

Minimum monthly test:

1. Export schema and data.
2. Restore into a temporary database.
3. Run health checks.
4. Verify memories and approvals exist.

## Files

Keep repo state in GitHub. Do not store secrets in git.
