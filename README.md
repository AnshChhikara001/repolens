# repolens

> 🚧 **Work in progress.** See the [roadmap](#roadmap) for current status.

Ask questions about any public GitHub repository, such as *"How does auth work here?"*, *"Which modules are the riskiest to change?"* or *"Write an onboarding guide"*. You get back a report where **every claim cites a `file:line` or a commit/PR**.

repolens pins the repository to a commit and indexes its Python and TypeScript code in Postgres, split into functions and classes with tree-sitter and searchable by keywords and by meaning. A model answers from the code it retrieves, and every citation is checked against the lines the model was actually shown before the answer is written. Each run logs its model calls, tokens and latency. It is plain Python with a small model layer for Gemini and Claude, no agent framework.

## Architecture (planned)

```mermaid
flowchart LR
    Q([Question + repo]) --> G{Guardrails<br/>+ fast path}
    G --> S[Supervisor<br/>plan / re-plan]
    S -- Send --> CN[Code Navigator<br/>hybrid RAG over code]
    S -- Send --> HA[History Analyst<br/>GitHub API + DuckDB]
    S -- Send --> DA[Dependency Analyst<br/>OSV advisories]
    CN --> S
    HA --> S
    DA --> S
    S --> RW[Report Writer<br/>cited findings only]
    RW --> V[Citation check] --> R([Report])
    RW -. human approval .-> I[(Issue in<br/>sandbox repo)]
```

- **Plan-and-execute supervisor.** It is built directly on `StateGraph`: independent steps fan out with `Send`, and the supervisor can re-plan up to twice.
- **Cost cap.** Each run has a USD budget. It switches to a cheaper model at 80% and stops gracefully at 100%.
- **Guardrails.** Repo content is scanned for prompt injections and secrets at ingest and always treated as untrusted data. The single write action requires human approval.
- **Verifiable output.** Citations are checked against the analysed commit before a report is returned.

Design decisions are recorded in [`docs/adr/`](docs/adr/).

## Development

Requires [uv](https://docs.astral.sh/uv/) and Docker.

```sh
uv sync
docker compose up -d        # Postgres with pgvector
cp .env.example .env        # then add your keys
uv run repolens doctor      # checks the database and keys
uv run repolens ingest fastapi/typer   # chunks and embeds a repo snapshot
uv run repolens ask fastapi/typer "How are CLI options parsed?"   # cited answer
uv run pytest               # database tests are skipped if Postgres isn't running
```

## Roadmap

- [x] **M0** Project scaffold, CI, local Postgres
- [x] **M1** End-to-end slice: ingest a repo snapshot, code Q&A with citations (CLI)
- [ ] **M2** Parallel specialists, re-planning, cost cap, tracing
- [ ] **M3** Guardrails, MCP tools with human approval, evaluation suite
- [ ] **M4** Streaming API + UI, public demo, evaluation results

## License

[MIT](LICENSE)
