# Security Model

## Defaults

- Keep credentials in environment variables or a secrets manager.
- Do not give OpenClaw direct database credentials.
- Require `X-Assistant-API-Key` for assistant API tool calls.
- Queue sensitive actions for approval.
- Keep iMessage on the Mac-side bridge.

## Sensitive Actions

Require approval for:

- sending texts or emails
- booking reservations
- purchases
- banking or financial actions
- external posts
- deleting user data

## Data Principle

Store the minimum raw personal data required. Prefer normalized records and summaries when raw content is not needed.
