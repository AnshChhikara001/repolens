# Hosting on Hugging Face Spaces, Neon and Langfuse Cloud

> **Superseded** by [ADR-0011](0011-one-agent-in-plain-python.md): repolens runs locally; a hosted demo may come back in M3.

The demo runs as one Docker image (FastAPI + Streamlit) on a free CPU Hugging Face Space. Postgres is Neon's free tier (pgvector) and tracing is Langfuse Cloud's free tier. Render's free instance (512 MB) can't hold the embedding, reranker and injection models together. Self-hosted Langfuse v3 (ClickHouse, Redis, object storage) is too heavy for the 8 GB development machine. Showcase runs are stored as static JSON so they load instantly even while the Space is waking from sleep.
