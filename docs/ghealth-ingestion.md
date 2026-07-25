# ghealth ingestion

Hippo Compass uses `ghealth` as its only Google Health data-plane client.
OpenClaw never receives Google OAuth files; it gets health context from the
Hippo Compass API and Postgres views.

The Compose `openclaw` image also contains the same pinned `ghealth` binary
for schema/help inspection, but deliberately has no `GHEALTH_CONFIG_DIR`
mount. The `ghealth-ingest` container is the only runtime with credentials.

## Secret directory and one-time authorization

On the VPS, create a root-only persistent directory outside this repository:

```bash
install -d -m 0700 /opt/hippo-secrets/ghealth
cp /secure/location/client_secret.json /opt/hippo-secrets/ghealth/client_secret.json
chmod 0600 /opt/hippo-secrets/ghealth/client_secret.json
```

Set `GHEALTH_CONFIG_HOST_PATH=/opt/hippo-secrets/ghealth` in `.env`, build the
service, and authorize once. The writable mount is intentional: `ghealth`
persists refreshed tokens in `credentials.json` and its timezone in
`config.toml`.

```bash
docker compose -f infra/docker-compose.yml --env-file .env --profile ghealth run --rm ghealth-ingest \
  ghealth config set timezone America/New_York
docker compose -f infra/docker-compose.yml --env-file .env --profile ghealth run --rm ghealth-ingest \
  ghealth auth login --non-interactive --scopes-preset readonly
# Open the returned auth_url, then complete with the returned code:
docker compose -f infra/docker-compose.yml --env-file .env --profile ghealth run --rm ghealth-ingest \
  ghealth auth login --complete '<code>'
docker compose -f infra/docker-compose.yml --env-file .env --profile ghealth run --rm ghealth-ingest \
  ghealth auth status --validate
```

Never use a health-data profile containing `cloud-platform`; it is rejected by
Google Health data endpoints. Keep any future webhook credentials in a separate
directory/profile.

## Migration and operation

Existing databases need the migration explicitly:

```bash
docker compose -f infra/docker-compose.yml --env-file .env --profile migrations run --rm db-migrate
docker compose -f infra/docker-compose.yml --env-file .env --profile ghealth up -d --build ghealth-ingest
```

For the optional local database, start `--profile local-db` first (or include
both `--profile local-db --profile migrations` when running the migration).

The service stores its CLI-discovered schemas in `ghealth_schema_snapshots`,
backfills 90 days in seven-day windows, and then syncs each initial type every
four hours using a 24-hour overlap. It follows any `nextPageToken`, stores raw
`dataPoints`/`rollupDataPoints` JSONB first, and projects only verified fields.

## Verified v1 field mappings

| Type / operation | Raw envelope | Typed fields |
| --- | --- | --- |
| `heart-rate list` | `dataPoints[].heartRate` | `sampleTime.physicalTime`, `beatsPerMinute` |
| `steps daily-rollup` | `rollupDataPoints[].steps` | `civilStartTime.date`, `countSum` |
| `sleep list` | `dataPoints[].sleep` | interval, summary minutes, type |
| `exercise list` | `dataPoints[].exercise` | interval, exercise type, title, `metricsSummary` |
| `weight list` | `dataPoints[].weight` | `sampleTime.physicalTime`, `weightGrams` |

Synthetic fixtures in `services/ghealth-ingest/tests/fixtures/` document these
mappings without containing personal data. New fields remain in
`ghealth_raw_points.payload` until intentionally promoted through a migration.
