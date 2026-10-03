# repolens

**Ask a question about a GitHub repository and get an answer where every claim cites `file:line`, checked against the pinned commit.**

repolens is an agentic code Q&A tool. One agent searches and reads the code until it can answer, a deterministic verifier drops every citation to lines the model wasn't shown, and a pinned eval measures how often it finds the right code. It's plain Python with a small model layer for Gemini and Claude and no agent framework, so every step is explainable.

```console
$ uv run repolens ask fastapi/typer@a80f6e5 "How does typer show help with Rich formatting?"
Snapshot: fastapi/typer@a80f6e5ecd74f32b983cca336a2f3cba98d9853a
Question: How does typer show help with Rich formatting?

Typer replaces the default Click help method with the rich_format_help function to provide Rich-formatted output [1]. This function utilizes a Rich Console to display usage, help text, and panels for arguments, options, and subcommands while supporting Markdown markup [2].

[1] Typer uses the `rich_format_help` function in `typer/rich_utils.py` to replace the default Click `format_help` method, providing Rich-formatted help output.
    typer/rich_utils.py:555-568
    typer/core.py:1208-1217
[2] The `rich_format_help` function uses a Rich `Console` to print usage, help text, and panels for arguments, options, and subcommands, supporting different markup modes like Markdown.
    typer/rich_utils.py:569-687
[3] Typer also provides `rich_format_error` to print Click exceptions using Rich panels and styling.
    typer/rich_utils.py:697-728

2 calls · 5,711 in / 480 out tokens · 22.5s
```

## How it works

```mermaid
flowchart LR
    subgraph ingest [repolens ingest]
        GH[GitHub tarball<br/>at a commit SHA] --> CH[tree-sitter<br/>Chunks] --> EM[OpenAI<br/>embeddings]
    end
    EM --> PG[(Postgres<br/>full-text + pgvector)]
    subgraph ask [repolens ask]
        Q([Question]) --> CN{Code Navigator<br/>≤ 8 Agent steps}
        CN -- search / read / define --> T[Tools]
        T -- excerpts --> CN
        T --> LR[Lines read]
        CN -- Findings --> V[Citation verifier]
        LR --> V
        V -- verified Findings --> RW[Report Writer] --> R([Report])
    end
    T <--> PG
```

- **Snapshots.** A repository is pinned to a commit SHA, downloaded as a tarball and split with tree-sitter into function-, class- and section-level Chunks of its Python and TypeScript code. Each Snapshot is embedded once, so citations stay valid and eval questions stay reproducible.
- **Hybrid search.** Postgres full-text search and pgvector similarity are fused with reciprocal rank fusion, then a small local cross-encoder reranks the candidates.
- **The Code Navigator.** A Run starts with a search for the question. Then each Agent step is one model call that returns one structured action: `search`, `read` lines of a file, `define` a symbol, or `answer` with Findings. The first step must call a Tool, so the model always looks past the first search. There's no native tool calling, so any model that returns JSON works. A Run takes at most 8 steps and is shown at most 1,500 lines.
- **Verified citations.** Every excerpt the model is shown is recorded. A Citation survives only if every cited line was shown and the symbol it names is there. The Report Writer then writes the answer from the verified Findings only.
- **Run log.** Each Run writes a JSON Lines file with every model call (tokens, latency), Agent step, Tool result and rejected Citation to `~/.repolens/runs/`.

Design decisions are recorded in [`docs/adr/`](docs/adr/) and the vocabulary in [`CONTEXT.md`](CONTEXT.md).

## Results

29 questions on five pinned repositories: [`fastapi/typer`](https://github.com/fastapi/typer), [`pallets/flask`](https://github.com/pallets/flask) and [`encode/httpx`](https://github.com/encode/httpx) (Python), [`sindresorhus/ky`](https://github.com/sindresorhus/ky) and [`colinhacks/zod`](https://github.com/colinhacks/zod) (TypeScript), each with the files and symbols a good answer cites ([`evals/questions.toml`](evals/questions.toml)). One-shot means the model answers from the first search alone. Two runs per setup. **[The short write-up](evals/README.md)** explains the method and the misses in two minutes.

| Model | Setup | File recall | Symbol recall | Citation validity | Input tokens | Run time | Est. cost |
|---|---|---|---|---|---|---|---|
| Gemini 3.1 Flash-Lite | one-shot | 64–68% | 45–49% | 99% | 5,432 | 11.5s | $0.0019 |
| Gemini 3.1 Flash-Lite | agent | 80% | 61% | 99% | 16,679 | 16.1s | $0.0049 |
| Claude Sonnet 5 | one-shot | 60% | 45% | 99–100% | 7,862 | 17.0s | $0.0259 |
| Claude Sonnet 5 | agent | **90–94%** | **88–92%** | 99–100% | 28,885 | 30.1s | $0.0710 |

Recall and validity are over the questions that got an answer; 3 of 58 one-shot Gemini Runs failed with provider overload errors (503), and 2 of 58 Sonnet 5 agent Runs with a timeout. Tokens, time and cost are means per question; cost is estimated at list prices. The typer and ky questions were recorded first (one-shot on 2026-09-30, agent on 2026-10-02), and the totals weight the two recordings by question count.

- **Searching and reading beats answering from one search.** On Claude Sonnet 5 the agent finds 90–94% of the expected files, against 60% one-shot, for about 3.7x the tokens. On flask, httpx and zod it finds all of them.
- **Gemini 3.1 Flash-Lite needs a push to look.** Requiring one Tool call before the answer took its file recall on typer and ky from 66–71% to 78%; it still answers right after that call in most Runs.
- **Citations stay valid.** The verifier kept 96–100% of Citations in every setup and run.
- **Retrieval still misses some code.** On two ky questions and one httpx question, test files that use the question's words crowd the source out of the search results.

Full tables and analysis: [agent vs one-shot on typer and ky](evals/results/agent.md), [flask, httpx and zod](evals/results/demo-repos.md), and the [one-shot baseline](evals/results/baseline.md) that kept the reranker.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and Docker. The default chat model, Gemini 3.1 Flash-Lite, runs on Google's free tier; embeddings cost a few cents per repository on OpenAI.

```sh
git clone https://github.com/AnshChhikara001/repolens.git && cd repolens
uv sync
docker compose up -d        # Postgres with pgvector
cp .env.example .env        # add GOOGLE_API_KEY and OPENAI_API_KEY
uv run repolens doctor      # checks the database and keys
uv run repolens ask fastapi/typer "How are CLI options parsed?"
```

`ask` ingests the repository on first use (`repolens ingest` does only that). The reranker model (about 80 MB) downloads on the first Run.

To use Claude, set `CHAT_MODEL=anthropic:claude-sonnet-5` and `ANTHROPIC_API_KEY`. Other settings are listed in [`.env.example`](.env.example).

### Run the eval

```sh
uv run repolens eval              # the agent, up to 8 Agent steps
uv run repolens eval --steps 1    # one-shot
uv run repolens eval --no-rerank  # search order instead of the reranker
```

It prints markdown tables like the ones in [`evals/results/`](evals/results/).

## Development

```sh
uv run pytest               # database tests are skipped if Postgres isn't running
uv run ruff check && uv run ruff format --check
uv run pyright              # strict mode
```

## Roadmap

- [x] **M0** Project scaffold, CI, local Postgres
- [x] **M1** End-to-end slice: ingest a repo snapshot, code Q&A with citations (CLI)
- [ ] **M2** Agentic Q&A, measured: one agent with search, read and define Tools, verified citations, a pinned eval
- [ ] **M3** *(optional)* Git history Tools, guardrails (prompt-injection scan, secret redaction), a hosted demo with a web UI

## License

[MIT](LICENSE)
