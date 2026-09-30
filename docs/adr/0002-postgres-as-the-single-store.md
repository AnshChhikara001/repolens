# Postgres (pgvector) is the single datastore

Postgres with pgvector stores the Snapshots and their Chunks: text, metadata, embeddings and a full-text index. A dedicated vector database (Chroma, Qdrant) would add a second service to run. We don't need its scale: repos are capped at 2,000 source files. Hybrid retrieval uses Postgres full-text search plus vector similarity, fused with reciprocal rank fusion, in one database.

## Consequences

- Each Run's log is a JSON Lines file on disk (`RUNS_DIR`), not a table. It is written once, read by people and scripts, and never queried by repolens, so it doesn't need the database. (It replaced a Postgres cost ledger when the cost cap was dropped, ADR-0011.)
