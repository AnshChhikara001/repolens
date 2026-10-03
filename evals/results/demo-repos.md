# The demo repos: flask, httpx and zod

Recorded 2026-10-02 with `repolens eval`, on the code at commit `3abb728` (the Run's first Agent step calls a Tool). These are the 9 [Eval questions](../questions.toml) added for the demo repos, 3 on each:

- [`pallets/flask@d73fa1c`](https://github.com/pallets/flask/tree/d73fa1cdcbd8b1465c151db8924ba58b1dd14e35) (Python web framework)
- [`encode/httpx@b5addb6`](https://github.com/encode/httpx/tree/b5addb64f0161ff6bfe94c124ef76f6a1fba5254) (Python HTTP client)
- [`colinhacks/zod@004d800`](https://github.com/colinhacks/zod/tree/004d800c9e3cd4c79930f55aa4ad080225b22efd) (TypeScript schema validation; the repo ships Zod 3 and Zod 4, so the questions name Zod 4)

Same setups as [agent vs one-shot](agent.md): **agent** (`--steps 8`) and **one-shot** (`--steps 1`), reranking on, two runs each. The 20 typer and ky questions weren't run again: their agent results are from the same code, on the same day, and one-shot Runs didn't change with it.

## Summary

| Setup | File recall | Symbol recall | Found nothing | Citation validity | Input tokens | Run time | Est. cost | Errors |
|---|---|---|---|---|---|---|---|---|
| Gemini 3.1 Flash-Lite, one-shot | 78% | 61% | 0% | 96% | 4,758 | 9.2s | $0.0018 | 0 / 18 |
| Gemini 3.1 Flash-Lite, agent | 83% | 61% | 0% | 100% | 10,483 | 16.7s | $0.0033 | 0 / 18 |
| Claude Sonnet 5, one-shot | 78% | 61% | 11% | 100% | 7,146 | 17.5s | $0.0245 | 0 / 18 |
| Claude Sonnet 5, agent | **100%** | **89%** | 0% | 100% | 15,988 | 25.8s | $0.0451 | 0 / 18 |

Both runs gave the same recall in every setup, so there are no ranges. Gemini also used the same tokens per question in both runs. Tokens, run time and cost are the mean per question over both runs.

## All 29 questions

Together with the [20 typer and ky questions](agent.md), weighted by question count (20 + 9). The typer/ky one-shot rows are the second recording; the agent rows are the 2026-10-02 update.

| Setup | File recall | Symbol recall | Input tokens | Est. cost |
|---|---|---|---|---|
| Gemini 3.1 Flash-Lite, one-shot | 64–68% | 45–49% | 5,432 | $0.0019 |
| Gemini 3.1 Flash-Lite, agent | 80% | 61% | 16,679 | $0.0049 |
| Claude Sonnet 5, one-shot | 60% | 45% | 7,862 | $0.0259 |
| Claude Sonnet 5, agent | **90–94%** | **88–92%** | 28,885 | $0.0710 |

## What it says

- **These 9 are easier than typer and ky.** In 7 of 9, the first search alone shows the expected file, and every setup cites it. So one-shot gets 78% here, against 52–64% on typer and ky. The 2 hard questions are where the setups differ.
- **Sonnet 5's agent finds every expected file**, in both runs. It answers after 1 or 2 Tool calls (2 steps: 15 Runs, 3 steps: 3), with 16 `read`s and 5 `search`es in all. No Run hit a limit.
- **Gemini's agent always stops after one Tool call** (2 steps in all 18 Runs); on typer and ky it did so in 15 of 20 Runs per run. It gains half of `httpx-content-decoding`, and nothing else.
- **The symbol misses are partial.** On `flask-before-request` and `zod-discriminated-union`, Sonnet 5's agent answers correctly from `Flask.preprocess_request` and the `$ZodDiscriminatedUnion` parser, but doesn't cite the second expected symbol (`Flask.full_dispatch_request`, `discriminatorMap`), which holds supporting code.
- **Citations stay valid**: 96–100%. The one rejected Citation is Gemini one-shot's on `httpx-content-decoding`: it cited `tests/test_decoders.py:14-75` after it was shown four separate tests in that range, not the lines between them.

## The two hard questions

**`httpx-content-decoding`: tests crowd out the source.** All 6 hits of the first search are tests (`tests/test_decoders.py` has `test_gzip`, `test_brotli`, ...), because they use the question's words. Sonnet 5 one-shot says "Nothing in encode/httpx answers this question", which is the honest answer from what it was shown. Gemini one-shot answers from the tests. Both agents search again with the code's words (Sonnet 5: `Content-Encoding decoder class SUPPORTED_DECODERS ContentDecoder`; Gemini: `class Response content decoding`) and find `Response._get_content_decoder`. Gemini doesn't cite `httpx/_decoders.py`. This is the same pattern as [ky's two missed questions](agent.md#why-ky-before-request-hooks-and-ky-json-body-are-missed).

**`zod-unknown-keys`: the model's search words decide.** The first search shows JSON Schema conversion code, not the parser. Gemini searches again with `Zod object strict loose unknown keys` and gets Zod 3 code and tests, so it never sees the Zod 4 parser. Gemini's one-shot answer says loose mode *strips* unknown keys, which is wrong (it keeps them). Sonnet 5 searches with the code's own words, `unrecognized_keys strict object parse catchall never`, and gets `handleCatchall` as the top hit. A valid Citation shows that the model saw the lines, not that the claim about them is right.

## Expected-file recall per question

Both runs of each setup.

| Question | Gemini one-shot | Gemini agent | Sonnet one-shot | Sonnet agent |
|---|---|---|---|---|
| flask-make-response | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 |
| flask-before-request | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 |
| flask-find-app | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 |
| httpx-redirect | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 |
| httpx-digest-auth | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 |
| httpx-content-decoding | 0/2, 0/2 | 1/2, 1/2 | 0/2, 0/2 | 2/2, 2/2 |
| zod-unknown-keys | 0/1, 0/1 | 0/1, 0/1 | 0/1, 0/1 | 1/1, 1/1 |
| zod-discriminated-union | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 |
| zod-treeify-error | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 |

## Per-question results, run 1

### Gemini 3.1 Flash-Lite, agent

| Question | Files | Symbols | Citations valid | Findings | Model s | Run s | Tokens in / out | Est. cost |
|---|---|---|---|---|---|---|---|---|
| flask-make-response | 1/1 | 1/1 | 4/4 | 4 | 14.4 | 25.7 | 10,730 / 588 | $0.0036 |
| flask-before-request | 1/1 | 1/2 | 5/5 | 3 | 16.4 | 23.0 | 5,749 / 575 | $0.0023 |
| flask-find-app | 1/1 | 1/1 | 4/4 | 4 | 11.7 | 14.1 | 13,423 / 574 | $0.0042 |
| httpx-redirect | 1/1 | 2/2 | 2/2 | 2 | 16.2 | 18.9 | 4,502 / 435 | $0.0018 |
| httpx-digest-auth | 1/1 | 1/2 | 2/2 | 2 | 9.1 | 12.8 | 6,155 / 351 | $0.0021 |
| httpx-content-decoding | 1/2 | 1/2 | 3/3 | 3 | 8.8 | 14.7 | 5,289 / 472 | $0.0020 |
| zod-unknown-keys | 0/1 | 0/1 | 5/5 | 3 | 8.8 | 14.0 | 20,345 / 510 | $0.0059 |
| zod-discriminated-union | 1/1 | 0/2 | 2/2 | 2 | 5.8 | 8.5 | 16,027 / 361 | $0.0045 |
| zod-treeify-error | 1/1 | 1/1 | 3/3 | 3 | 8.2 | 11.0 | 12,124 / 506 | $0.0038 |

### Gemini 3.1 Flash-Lite, one-shot

| Question | Files | Symbols | Citations valid | Findings | Model s | Run s | Tokens in / out | Est. cost |
|---|---|---|---|---|---|---|---|---|
| flask-make-response | 1/1 | 1/1 | 3/3 | 3 | 6.6 | 9.2 | 4,753 / 454 | $0.0019 |
| flask-before-request | 1/1 | 1/2 | 3/3 | 2 | 3.6 | 6.2 | 2,859 / 372 | $0.0013 |
| flask-find-app | 1/1 | 1/1 | 4/4 | 4 | 6.5 | 8.8 | 6,806 / 543 | $0.0025 |
| httpx-redirect | 1/1 | 2/2 | 2/2 | 2 | 6.0 | 8.4 | 2,318 / 389 | $0.0012 |
| httpx-digest-auth | 1/1 | 1/2 | 2/2 | 2 | 6.2 | 8.5 | 3,163 / 359 | $0.0013 |
| httpx-content-decoding | 0/2 | 0/2 | 1/2 | 1 | 8.3 | 10.8 | 1,811 / 242 | $0.0008 |
| zod-unknown-keys | 0/1 | 0/1 | 2/2 | 2 | 6.9 | 9.3 | 6,843 / 299 | $0.0022 |
| zod-discriminated-union | 1/1 | 1/2 | 2/2 | 2 | 7.3 | 9.6 | 8,075 / 335 | $0.0025 |
| zod-treeify-error | 1/1 | 1/1 | 4/4 | 4 | 9.1 | 11.6 | 6,191 / 581 | $0.0024 |

### Claude Sonnet 5, agent

| Question | Files | Symbols | Citations valid | Findings | Model s | Run s | Tokens in / out | Est. cost |
|---|---|---|---|---|---|---|---|---|
| flask-make-response | 1/1 | 1/1 | 6/6 | 6 | 18.0 | 33.1 | 13,352 / 1,392 | $0.0406 |
| flask-before-request | 1/1 | 1/2 | 3/3 | 3 | 17.1 | 25.0 | 9,001 / 1,164 | $0.0296 |
| flask-find-app | 1/1 | 1/1 | 4/4 | 4 | 18.0 | 25.0 | 18,278 / 1,456 | $0.0511 |
| httpx-redirect | 1/1 | 2/2 | 4/4 | 4 | 21.9 | 30.1 | 8,076 / 1,174 | $0.0279 |
| httpx-digest-auth | 1/1 | 2/2 | 4/4 | 4 | 14.4 | 23.2 | 15,851 / 1,201 | $0.0437 |
| httpx-content-decoding | 2/2 | 2/2 | 7/7 | 5 | 19.6 | 33.5 | 17,218 / 1,592 | $0.0504 |
| zod-unknown-keys | 1/1 | 1/1 | 4/4 | 4 | 16.2 | 26.5 | 28,258 / 1,255 | $0.0691 |
| zod-discriminated-union | 1/1 | 1/2 | 6/6 | 6 | 22.8 | 29.5 | 21,351 / 1,703 | $0.0597 |
| zod-treeify-error | 1/1 | 1/1 | 4/4 | 4 | 15.0 | 22.3 | 16,439 / 1,275 | $0.0456 |

### Claude Sonnet 5, one-shot

| Question | Files | Symbols | Citations valid | Findings | Model s | Run s | Tokens in / out | Est. cost |
|---|---|---|---|---|---|---|---|---|
| flask-make-response | 1/1 | 1/1 | 6/6 | 5 | 11.9 | 18.5 | 7,004 / 1,200 | $0.0260 |
| flask-before-request | 1/1 | 1/2 | 3/3 | 3 | 9.6 | 19.7 | 4,777 / 708 | $0.0166 |
| flask-find-app | 1/1 | 1/1 | 4/4 | 4 | 9.6 | 17.2 | 9,473 / 877 | $0.0277 |
| httpx-redirect | 1/1 | 2/2 | 3/3 | 3 | 11.1 | 16.4 | 4,353 / 903 | $0.0177 |
| httpx-digest-auth | 1/1 | 1/2 | 4/4 | 4 | 10.3 | 16.2 | 5,350 / 935 | $0.0201 |
| httpx-content-decoding | 0/2 | 0/2 | 0/0 | 0 | 4.7 | 8.1 | 2,869 / 293 | $0.0087 |
| zod-unknown-keys | 0/1 | 0/1 | 4/4 | 4 | 12.8 | 18.3 | 10,376 / 1,016 | $0.0309 |
| zod-discriminated-union | 1/1 | 1/2 | 5/5 | 5 | 14.5 | 20.2 | 11,042 / 1,300 | $0.0351 |
| zod-treeify-error | 1/1 | 1/1 | 8/8 | 6 | 14.9 | 20.9 | 8,830 / 1,542 | $0.0331 |
