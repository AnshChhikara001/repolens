# Tests after source in search

Recorded 2026-10-03 with `repolens eval` on all 29 [Eval questions](../questions.toml), at commits `018ec06` and `f8c1518`, which search these 5 repos the same way. Since then, a search puts test files after all other code, unless its query mentions tests ([ADR-0012](../../docs/adr/0012-tests-after-source-in-search.md)). The agent's prompt says so too.

Same setups as before: **agent** (`--steps 8`) and **one-shot** (`--steps 1`), reranking on. Gemini ran twice in both setups and Sonnet 5's agent twice; Sonnet 5 one-shot ran once to save quota. `CHAT_TIMEOUT` was 300s (120s before), so no Run timed out.

## Summary

Before is the [all-29 totals](demo-repos.md#all-29-questions) of the last recording.

| Setup | File recall | Symbol recall | Citation validity | Input tokens | Run time | Est. cost | Errors |
|---|---|---|---|---|---|---|---|
| Gemini 3.1 Flash-Lite, one-shot | 64–68% → **72%** | 45–49% → 52% | 100% | 5,432 → 5,184 | 7.9s | $0.0019 → $0.0020 | 0 / 58 |
| Gemini 3.1 Flash-Lite, agent | 80% → **84%** | 61% → **72%** | 100% | 16,679 → 13,751 | 12.1s | $0.0049 → $0.0042 | 0 / 58 |
| Claude Sonnet 5, one-shot (1 run) | 60% → **69%** | 45% → 50% | 100% | 7,862 → 7,611 | 16.3s | $0.0259 → $0.0247 | 0 / 29 |
| Claude Sonnet 5, agent | 90–94% → **93–97%** | 88–92% → 86–91% | 97–99% | 28,885 → 22,354 | 27.6s | $0.0710 → $0.0580 | 0 / 58 |

Gemini gave the same answers, with the same tokens, in both runs. Tokens, run time and cost are the mean per question.

The change is kept: file recall rose in every setup.

## What it says

- **The first search finds more of the code.** It shows an expected file for 26 of 29 questions, against 21 before. All 3 questions the change was for are among them: `ky-before-request-hooks` now gets `Ky.#runBeforeRequestHooks` itself, which wasn't among the 24 candidates before.
- **One-shot gains the most.** Both models now answer `httpx-content-decoding` and `ky-before-request-hooks` from the first search, and half of `ky-retry-after`. Sonnet 5 one-shot used to say it couldn't answer `httpx-content-decoding`.
- **Agents get more for fewer tokens.** Gemini's agent gets `httpx-content-decoding` fully, and its symbol recall rises by 11 points. Sonnet 5's agent gets every ky question in run 1, and uses about a fifth fewer input tokens.
- **Sonnet 5's symbol recall is about the same**: 86–91% against 88–92%. Its two runs differ in symbols on 6 questions, so the ranges are within run-to-run noise.
- **Citations stay valid**: 97–100%.

## What it still misses

- **`ky-json-body`: type declarations, not tests.** The first search shows 5 Chunks of `source/types/*.ts`, whose JSDoc names every option, and only the field list of the `Ky` class. The answer is in `Ky.constructor`. Gemini answers from the JSDoc. Sonnet 5 searched 7 more times in each run; in run 1 the last search showed the constructor.
- **`zod-unknown-keys`: an equally good file.** The first search now shows `core/compile.ts`, Zod's compiled fast path, next to the expected `core/schemas.ts`. `compile.ts` generates the same strict and loose checks as the parser. Every setup now answers correctly, but none cites the expected file, so the dataset could accept `compile.ts` too. Gemini one-shot's answer was wrong before (it said loose mode strips unknown keys). Before, Sonnet 5's agent searched with the parser's words and cited `handleCatchall`.
- **`typer-context-parameter`, `typer-find-app`**: Gemini still misses both, as before. Sonnet 5's agent gets them.

## Expected-file recall per question

Both runs of each setup (one for Sonnet 5 one-shot).

| Question | Gemini one-shot | Gemini agent | Sonnet one-shot | Sonnet agent |
|---|---|---|---|---|
| typer-params-to-options | 1/2, 1/2 | 2/2, 2/2 | 1/2 | 2/2, 2/2 |
| typer-single-command | 1/1, 1/1 | 1/1, 1/1 | 0/1 | 1/1, 1/1 |
| typer-enum-choices | 1/1, 1/1 | 1/1, 1/1 | 1/1 | 1/1, 1/1 |
| typer-context-parameter | 0/1, 0/1 | 0/1, 0/1 | 0/1 | 1/1, 1/1 |
| typer-annotated | 0/1, 0/1 | 1/1, 1/1 | 0/1 | 1/1, 1/1 |
| typer-pretty-exceptions | 1/1, 1/1 | 1/1, 1/1 | 1/1 | 1/1, 1/1 |
| typer-rich-help | 2/2, 2/2 | 2/2, 2/2 | 2/2 | 2/2, 2/2 |
| typer-did-you-mean | 1/1, 1/1 | 1/1, 1/1 | 1/1 | 1/1, 1/1 |
| typer-install-completion | 1/1, 1/1 | 1/1, 1/1 | 1/1 | 1/1, 1/1 |
| typer-cli-runner | 1/1, 1/1 | 1/1, 1/1 | 1/1 | 1/1, 1/1 |
| typer-find-app | 0/1, 0/1 | 0/1, 0/1 | 0/1 | 1/1, 1/1 |
| ky-retry-decision | 1/2, 1/2 | 1/2, 1/2 | 1/2 | 2/2, 2/2 |
| ky-retry-after | 1/2, 1/2 | 2/2, 2/2 | 1/2 | 2/2, 2/2 |
| ky-retry-delay | 1/1, 1/1 | 1/1, 1/1 | 1/1 | 1/1, 1/1 |
| ky-timeout | 1/2, 1/2 | 2/2, 2/2 | 1/2 | 2/2, 2/2 |
| ky-before-request-hooks | 1/1, 1/1 | 1/1, 1/1 | 1/1 | 1/1, 1/1 |
| ky-extend | 2/2, 2/2 | 2/2, 2/2 | 2/2 | 2/2, 2/2 |
| ky-json-body | 0/1, 0/1 | 0/1, 0/1 | 0/1 | 1/1, 0/1 |
| ky-prefix-base-url | 1/1, 1/1 | 1/1, 1/1 | 1/1 | 1/1, 1/1 |
| ky-max-response-size | 0/1, 0/1 | 1/1, 1/1 | 0/1 | 1/1, 1/1 |
| flask-make-response | 1/1, 1/1 | 1/1, 1/1 | 1/1 | 1/1, 1/1 |
| flask-before-request | 1/1, 1/1 | 1/1, 1/1 | 1/1 | 1/1, 1/1 |
| flask-find-app | 1/1, 1/1 | 1/1, 1/1 | 1/1 | 1/1, 1/1 |
| httpx-redirect | 1/1, 1/1 | 1/1, 1/1 | 1/1 | 1/1, 1/1 |
| httpx-digest-auth | 1/1, 1/1 | 1/1, 1/1 | 1/1 | 1/1, 1/1 |
| httpx-content-decoding | 2/2, 2/2 | 2/2, 2/2 | 2/2 | 2/2, 2/2 |
| zod-unknown-keys | 0/1, 0/1 | 0/1, 0/1 | 0/1 | 0/1, 0/1 |
| zod-discriminated-union | 1/1, 1/1 | 1/1, 1/1 | 1/1 | 1/1, 1/1 |
| zod-treeify-error | 1/1, 1/1 | 1/1, 1/1 | 1/1 | 1/1, 1/1 |
