# Postgres (pgvector) is the single datastore

Postgres with pgvector stores the chunk vectors and metadata, the LangGraph checkpointer (threads, human-approval `interrupt` state) and the cost ledger. A dedicated vector database (Chroma, Qdrant) would add a second service to run locally and host for free. We don't need its scale: repos are capped at about 2k files. Hybrid retrieval uses Postgres full-text search plus vector similarity, fused with reciprocal rank fusion, in one database.

## Consequences

The hosted demo needs a free Postgres with pgvector (Neon). History Analyst's analytical queries still run in DuckDB in-process, because they operate on per-run data and don't need to persist.
