# Memory Model

Memory has three layers:

- Raw records: immutable-ish data imported from apps.
- Semantic memory: summarized preferences, facts, lessons, goals, and writing style.
- Episodic log: decisions, recommendations, approvals, and feedback.

Retrieval should combine:

- direct filters by kind/source/date
- vector similarity through pgvector
- recency and confidence ranking

Sensitive facts should include source, confidence, and audit history. Memory should be editable and deletable by the user.
