# Does repolens find the right code?

repolens answers questions about a codebase and points to the lines that back each answer. This page shows how it is measured, and what it still gets wrong. It's a 2-minute read.

## The test

- **29 questions on 5 real open-source projects**: [typer](https://github.com/fastapi/typer), [flask](https://github.com/pallets/flask) and [httpx](https://github.com/encode/httpx) in Python, [ky](https://github.com/sindresorhus/ky) and [zod](https://github.com/colinhacks/zod) in TypeScript. For example: *"When httpx follows a redirect, how does it pick the new method and which headers does it drop?"*
- **The right answer is written down first.** For every question, the files and functions that hold the answer were looked up in the source and saved with it ([`questions.toml`](questions.toml)).
- **Each project is pinned to one commit**, so every run sees exactly the same code.
- **A program does the scoring**, not a person or another AI. It checks whether the answer points to the expected files.
- **A citation counts only if the model was shown those lines.** A verifier drops every citation to lines the model wasn't shown, so it can't invent a plausible file and line number.
- **Every setup runs twice**, and errors (a model timeout, an overloaded API) are counted, not hidden.

Each question is answered in two ways. **One-shot**: the model gets one search of the code and must answer from it. **Agent**: the model can also search again, read files and look up definitions, up to 8 times, before it answers.

## The result

How often the answer points to the right file, over all 29 questions:

| Model | One-shot | Agent | Cost per question (agent) |
|---|---|---|---|
| Claude Sonnet 5 | 60% | **90–94%** | about 7 cents |
| Gemini 3.1 Flash-Lite | 64–68% | 80% | under half a cent |

Ranges are the two runs. Letting the model look further lifts Claude Sonnet 5 by about 30 points. The small, cheap Gemini model gains less: it usually looks once more and then answers.

## What it still misses

Most misses have one cause, seen in ky and httpx. When the test files use the question's words, they fill the search results and push the real code out. On *"How does httpx choose how to decompress a response body?"*, all 6 first hits are tests. With only those, Claude Sonnet 5 says it can't answer, and Gemini answers from the tests. As an agent, Claude Sonnet 5 searches again with the code's own words (`Content-Encoding`, `decoder`) and finds it; Gemini finds half of it. On two ky questions, even that usually isn't enough.

The other cause is the model's search words. On a zod question, Gemini searches with the question's words and gets the older Zod 3 code; Claude Sonnet 5 searches with the names the code uses and finds the Zod 4 parser.

So the next gain is in **retrieval, not the model**: rank source files above tests, so that the first search shows the code that does the work.

## Limits

- 29 questions is a small set, and the same person wrote the questions and built the tool.
- The score checks that the answer points to the right place, not that every sentence is right. A valid citation shows that the model saw the lines, not that its claim about them is true ([an example](results/demo-repos.md#the-two-hard-questions)).
- The 9 flask, httpx and zod questions were added later and are easier: one search alone finds the right file for 7 of them.

## The details

- [Agent vs one-shot on typer and ky](results/agent.md): the 20 first questions, with per-question tables.
- [flask, httpx and zod](results/demo-repos.md): the 9 newer questions, and the totals over all 29.
- [The one-shot baseline](results/baseline.md): search with and without the reranker.
- Run it yourself: `uv run repolens eval` (see the [README](../README.md#run-the-eval)).
