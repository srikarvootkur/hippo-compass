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
   - Authorized redirect URI for local/tunneled setup:

     ```text
     http://localhost:8080/connectors/google-health/oauth/callback
     ```

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

## Safety

- Read-only only.
- No medical diagnosis.
- No real health payloads in git.
- OpenClaw should call Hippo Compass endpoints; it should not store Google OAuth credentials.
