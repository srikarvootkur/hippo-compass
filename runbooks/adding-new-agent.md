# Adding A New Agent Framework

1. Keep Postgres unchanged.
2. Keep `assistant-api` endpoints unchanged.
3. Decide whether the new framework is a shell, durable workflow engine, or specialist worker.
4. Add shells as clients of `assistant-api`.
5. Add durable workflow changes in `langgraph-workflows`.
6. Add focused specialist agents behind LangGraph when useful.
7. Test memory search/write and approval behavior.

The new framework is replaceable. The assistant API and database are the product boundary.
