# Google Health Connector

Hippo Compass can connect to Google Health API as a read-only source for Fitbit-backed activity and fitness data.

Source doc: <https://developers.google.com/health/codelabs/make-your-first-api-call>

## What This Connector Does

- Runs behind `assistant-api`.
- Uses Google OAuth with the Google Health readonly activity/fitness scope.
- Stores tokens in Postgres `source_connections`, not in OpenClaw.
- Stores imported records in `source_records`.
- Starts with the `exercise` data type.

## Google Cloud Setup

1. Create or select a Google Cloud project.
2. Enable **Google Health API**.
3. Configure the OAuth consent screen.
4. Add yourself as a test user while the app is in Testing.
5. Create OAuth credentials:
   - Application type: Web application
   - Authorized JavaScript origin for local/tunneled setup:

     ```text
     http://localhost:8080
     ```

   - Authorized redirect URI for local/tunneled setup:

     ```text
     http://localhost:8080/connectors/google-health/oauth/callback
     ```

     Do not put the callback path in Authorized JavaScript origins, and do not add a trailing slash unless your `.env` uses the exact same trailing slash.

   - Later production URI after DNS/Caddy:

     ```text
     https://assistant.yourdomain.com/connectors/google-health/oauth/callback
     ```

6. Add the Google Health API scope:

   ```text
   https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly
   ```

## Environment

Set these in `.env`:

```text
GOOGLE_HEALTH_CLIENT_ID=your-client-id
GOOGLE_HEALTH_CLIENT_SECRET=your-client-secret
GOOGLE_HEALTH_REDIRECT_URI=http://localhost:8080/connectors/google-health/oauth/callback
GOOGLE_HEALTH_SCOPES=https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly
```

Use the `GOOGLE_HEALTH_` names exactly. Generic names like `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are not read by this connector.

Do not commit `.env` or OAuth tokens.

## First OAuth Flow

If the assistant API is on the VPS and no DNS is configured, open an SSH tunnel from your Mac:

```bash
ssh -L 8080:localhost:8080 root@YOUR_SERVER_IP
```

Start OAuth:

```bash
curl -H "X-Assistant-API-Key: YOUR_ASSISTANT_API_KEY" \
  http://localhost:8080/connectors/google-health/oauth/start
```

Open the returned `authorization_url` in your browser. After consent, Google redirects to the callback URL, and Hippo Compass stores the tokens.

If your terminal prints JSON, copy only the value inside `authorization_url`; do not paste the whole JSON response into the browser address bar.

Check status:

```bash
curl -H "X-Assistant-API-Key: YOUR_ASSISTANT_API_KEY" \
  http://localhost:8080/connectors/google-health/status
```

Run sync:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-Assistant-API-Key: YOUR_ASSISTANT_API_KEY" \
  -d '{"data_type":"exercise"}' \
  http://localhost:8080/connectors/google-health/sync
```

Expected result:

```json
{
  "source_name": "google_health",
  "record_type": "exercise",
  "synced_count": 25,
  "records": [
    {
      "external_id": "users/.../dataPoints/...",
      "occurred_at": "2026-06-06T03:55:04.257000+00:00",
      "normalized_payload": {}
    }
  ]
}
```

The exact count and records depend on your Google/Fitbit data. The `normalized_payload` object will contain the extracted platform, exercise type, interval, calories, distance, steps, and active zone minutes when Google provides them. Running the sync multiple times should update existing rows by `external_id`, not create duplicates.

## Stored Data

Imported records use:

```text
source_name = google_health
record_type = exercise
external_id = Google Health data point name
raw_payload = full Google Health API data point
normalized_payload = selected exercise fields
```

Normalized fields include platform, recording method, exercise type, interval, calories, distance, steps, and active zone minutes.

Google timestamps arrive as strings such as `2026-06-06T03:55:04.257Z`; the API parses them before writing to Postgres. If you see an asyncpg error saying it expected a datetime but got a string, rebuild/restart `assistant-api` with the latest code:

```bash
cd ~/hippo-compass
docker compose -f infra/docker-compose.yml --env-file .env --profile local-db up -d --build assistant-api
```

If your local database was created before `db/migrations/002_google_health.sql`, apply the migration or rebuild the local database before OAuth. The connector depends on a unique `source_connections(source_name)` constraint for token upserts.

## Safety

- Read-only only.
- No medical diagnosis.
- No real health payloads in git.
- OpenClaw should call Hippo Compass endpoints; it should not store Google OAuth credentials.
- Rotate any OAuth client secret, Telegram token, GitHub token, or gateway token that was accidentally pasted into chat, logs, screenshots, or shell history.
