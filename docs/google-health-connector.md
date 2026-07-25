# Google Health Connector (retired direct path)

Hippo Compass previously called Google Health's OAuth and data endpoints from
`assistant-api`. That connector is retired. `ghealth-ingest` is now the sole
Google Health data-plane client and is responsible for OAuth token refresh,
schema discovery, pagination, backfills, and overlapping syncs.

Follow [ghealth-ingestion.md](ghealth-ingestion.md) for VPS setup. Do not set
`GOOGLE_HEALTH_CLIENT_ID`, `GOOGLE_HEALTH_CLIENT_SECRET`, or Google Health
scopes in Hippo Compass `.env`; keep `client_secret.json`, `credentials.json`,
and `config.toml` in the root-owned ghealth secret directory instead.
