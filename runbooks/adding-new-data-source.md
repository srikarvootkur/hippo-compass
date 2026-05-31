# Adding A New Data Source

1. Create connector credentials outside git.
2. Import raw payloads to `source_records`.
3. Normalize into typed JSON fields.
4. Generate memory candidates only for durable facts.
5. Add audit logs.
6. Add tests using mock payloads.
7. Use LangGraph if the connector needs retries, approvals, or multi-step review.

Start read-only. Add write actions only behind approvals.
