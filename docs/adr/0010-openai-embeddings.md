# Hosted OpenAI embeddings instead of local bge-small

Chunks and questions are embedded with OpenAI `text-embedding-3-small` (1536 dimensions) instead of bge-small running on CPU. The development machine has 8 GB of RAM, where a local embedding model would compete for memory with the cross-encoder reranker and make ingesting a 2,000-file repo slow. At about $0.02 per million tokens, a typical repository costs well under a cent to embed, and a 2,000-file one a few cents. Embeddings are stored per Snapshot (ADR-0008), so each Snapshot is paid for once. Search embeds each query with the same model.

## Considered Options

- **bge-small on CPU (the original plan):** free, but slow to ingest with and memory we need for the reranker.
- **Gemini embeddings on the free tier:** free, but they would share the daily request quota the chat models already depend on.

## Consequences

- `OPENAI_API_KEY` is required for ingest and retrieval. Tests use a fake embedder and need no key.
- The vector column is fixed at 1536 dimensions. Changing the model means re-ingesting.
- A hosted demo, if one is built, must not ingest new repositories on our key.
