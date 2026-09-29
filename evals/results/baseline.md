# Baseline: one-shot Code Navigator

Recorded 2026-09-29 with `repolens eval` on [`evals/questions.toml`](../questions.toml): 20 questions, 11 on `fastapi/typer@a80f6e5` and 9 on `sindresorhus/ky@0d59458`.

The Code Navigator here is one-shot. Hybrid search (full-text + vector, fused with RRF) finds 24 Chunks, the cross-encoder reranker keeps the best 6, and the model answers from those 6 in a single call. With `--no-rerank` it gets the top 6 search results instead.

## Summary

Each metric is over the questions that got an answer. Errors are counted separately.

| Setup | Runs | File recall | Symbol recall | Found nothing | Citation validity | Input tokens | Run time | Est. cost | Errors |
|---|---|---|---|---|---|---|---|---|---|
| Gemini 3.1 Flash-Lite, rerank | 2 | 57% | 38% | 0% | 100% | 7,246 | 13.8s | $0.0025 | 0 / 40 |
| Gemini 3.1 Flash-Lite, no rerank | 2 | 45% | 39–40% | 0% | 100% | 8,867 | 12.8s | $0.0029 | 1 / 40 |
| Claude Sonnet 5, rerank | 2 | 50–53% | 36–37% | 5–17% | 99–100% | 18,349 | 22.5s | $0.0544 | 2 / 40 |
| Claude Sonnet 5, no rerank | 2 | 50–53% | 44–45% | 0–6% | 97–100% | 30,722 | 25.3s | $0.0840 | 3 / 40 |

Ranges are the two runs. Tokens, run time and cost are the mean per question over both runs. Gemini gave the same scores on every run. One more no-rerank run hit 503s from the provider on 4 questions and was repeated; the tables below show the complete Gemini runs. The Claude errors are answers that didn't fit the output schema, and one timeout.

## What the baseline says

- **Retrieval is the bottleneck.** Citations are almost always valid, but only about half of the expected files get cited. The model can only cite the 6 Chunks it was shown. Some questions are missed by every setup: `typer-context-parameter`, `typer-annotated`, `ky-retry-after`, `ky-before-request-hooks`, `ky-max-response-size`. This is what the agentic Code Navigator (#21) has to improve.
- **Symbol recall is low** partly because models often cite lines without naming the symbol.

## Reranker: kept

- On Gemini 3.1 Flash-Lite, the public default, reranking raises file recall from 45% to 57%. That's 12 points, about 2.5 questions' worth.
- It cuts input tokens by about 18% on Gemini and 40% on Sonnet 5. The reranked Chunks are more relevant, so the prompt carries less noise.
- On Sonnet 5 it doesn't change file recall. It lowers symbol recall (about 37% vs 45%), and it found nothing on a few more questions.
- It adds about 2s of CPU per Run: the gap between run time and model time grows from ~0.8s to ~2.7s on Gemini. It also downloads an 80 MB model on first use.

It helps the default model on the main metric and makes every Run cheaper, so it stays. #21 compares again with the agent's own search.

## Per-question results

### Gemini 3.1 Flash-Lite, reranking on

| Metric | Value |
|---|---|
| Questions | 20 (0 errors) |
| Citation validity | 80/80 (100%) |
| Expected-file recall | 57% |
| Expected-symbol recall | 38% (20 questions) |
| Found nothing | 0/20 (0%) |
| Model latency | 12.1s mean |
| Run time | 14.9s mean |
| Tokens | 7,246 in / 437 out mean |
| Est. cost | $0.0025 mean, $0.0493 total |

| Question | Files | Symbols | Citations valid | Findings | Model s | Run s | Tokens in / out | Est. cost |
|---|---|---|---|---|---|---|---|---|
| typer-params-to-options | 1/2 | 1/2 | 4/4 | 4 | 7.5 | 11.9 | 10,137 / 545 | $0.0034 |
| typer-single-command | 1/1 | 0/1 | 1/1 | 1 | 10.9 | 13.6 | 8,979 / 168 | $0.0025 |
| typer-enum-choices | 1/1 | 1/2 | 3/3 | 3 | 16.3 | 19.2 | 2,589 / 410 | $0.0013 |
| typer-context-parameter | 0/1 | 0/2 | 2/2 | 1 | 5.0 | 7.5 | 2,715 / 197 | $0.0010 |
| typer-annotated | 0/1 | 0/1 | 6/6 | 3 | 7.4 | 9.8 | 7,439 / 571 | $0.0027 |
| typer-pretty-exceptions | 1/1 | 2/2 | 4/4 | 4 | 16.5 | 19.4 | 3,782 / 515 | $0.0017 |
| typer-rich-help | 2/2 | 1/1 | 5/5 | 3 | 11.1 | 13.5 | 5,641 / 568 | $0.0023 |
| typer-did-you-mean | 1/1 | 0/1 | 3/3 | 2 | 56.7 | 59.2 | 7,832 / 351 | $0.0025 |
| typer-install-completion | 1/1 | 2/3 | 2/2 | 2 | 9.0 | 12.9 | 2,890 / 333 | $0.0012 |
| typer-cli-runner | 1/1 | 1/2 | 2/2 | 2 | 6.7 | 9.8 | 2,916 / 270 | $0.0011 |
| typer-find-app | 0/1 | 0/1 | 4/4 | 3 | 12.9 | 15.5 | 5,786 / 501 | $0.0022 |
| ky-retry-decision | 1/2 | 1/1 | 7/7 | 3 | 10.0 | 12.8 | 7,579 / 637 | $0.0029 |
| ky-retry-after | 0/2 | 0/2 | 8/8 | 5 | 17.3 | 20.3 | 10,894 / 651 | $0.0037 |
| ky-retry-delay | 1/1 | 1/1 | 7/7 | 5 | 9.9 | 12.2 | 9,411 / 671 | $0.0034 |
| ky-timeout | 1/2 | 0/2 | 5/5 | 3 | 6.1 | 8.7 | 4,124 / 459 | $0.0017 |
| ky-before-request-hooks | 0/1 | 0/1 | 4/4 | 4 | 9.5 | 12.2 | 11,856 / 462 | $0.0037 |
| ky-extend | 2/2 | 1/2 | 5/5 | 4 | 6.3 | 10.0 | 8,001 / 529 | $0.0028 |
| ky-json-body | 0/1 | 0/1 | 4/4 | 3 | 6.6 | 9.5 | 12,157 / 429 | $0.0037 |
| ky-prefix-base-url | 1/1 | 1/1 | 2/2 | 2 | 8.6 | 11.1 | 9,121 / 288 | $0.0027 |
| ky-max-response-size | 0/1 | 0/1 | 2/2 | 1 | 6.9 | 9.4 | 11,062 / 186 | $0.0030 |

### Gemini 3.1 Flash-Lite, reranking off

| Metric | Value |
|---|---|
| Questions | 20 (0 errors) |
| Citation validity | 89/89 (100%) |
| Expected-file recall | 45% |
| Expected-symbol recall | 40% (20 questions) |
| Found nothing | 0/20 (0%) |
| Model latency | 11.5s mean |
| Run time | 12.3s mean |
| Tokens | 8,907 in / 480 out mean |
| Est. cost | $0.0029 mean, $0.0589 total |

| Question | Files | Symbols | Citations valid | Findings | Model s | Run s | Tokens in / out | Est. cost |
|---|---|---|---|---|---|---|---|---|
| typer-params-to-options | 1/2 | 1/2 | 3/3 | 3 | 18.2 | 19.2 | 10,448 / 472 | $0.0033 |
| typer-single-command | 1/1 | 1/1 | 2/2 | 1 | 15.7 | 16.1 | 7,794 / 214 | $0.0023 |
| typer-enum-choices | 0/1 | 0/2 | 4/4 | 3 | 14.7 | 15.5 | 5,948 / 451 | $0.0022 |
| typer-context-parameter | 0/1 | 0/2 | 2/2 | 2 | 8.7 | 9.4 | 5,915 / 281 | $0.0019 |
| typer-annotated | 0/1 | 0/1 | 8/8 | 4 | 8.3 | 9.2 | 10,681 / 733 | $0.0038 |
| typer-pretty-exceptions | 1/1 | 2/2 | 4/4 | 4 | 7.0 | 7.6 | 4,383 / 544 | $0.0019 |
| typer-rich-help | 1/2 | 1/1 | 4/4 | 3 | 16.0 | 16.7 | 6,996 / 435 | $0.0024 |
| typer-did-you-mean | 0/1 | 0/1 | 2/2 | 1 | 6.4 | 7.2 | 7,313 / 209 | $0.0021 |
| typer-install-completion | 1/1 | 3/3 | 3/3 | 3 | 5.5 | 6.2 | 3,654 / 439 | $0.0016 |
| typer-cli-runner | 1/1 | 1/2 | 2/2 | 2 | 6.3 | 6.8 | 2,424 / 276 | $0.0010 |
| typer-find-app | 1/1 | 1/1 | 4/4 | 3 | 9.5 | 10.1 | 3,292 / 512 | $0.0016 |
| ky-retry-decision | 1/2 | 1/1 | 7/7 | 6 | 9.0 | 10.1 | 9,814 / 785 | $0.0036 |
| ky-retry-after | 0/2 | 0/2 | 8/8 | 5 | 16.4 | 17.5 | 12,856 / 725 | $0.0043 |
| ky-retry-delay | 0/1 | 0/1 | 9/9 | 5 | 10.5 | 11.3 | 12,074 / 808 | $0.0042 |
| ky-timeout | 1/2 | 0/2 | 6/6 | 5 | 8.5 | 9.2 | 12,446 / 650 | $0.0041 |
| ky-before-request-hooks | 0/1 | 0/1 | 5/5 | 3 | 17.8 | 18.2 | 12,015 / 455 | $0.0037 |
| ky-extend | 0/2 | 0/2 | 7/7 | 4 | 11.5 | 12.2 | 12,008 / 623 | $0.0039 |
| ky-json-body | 1/1 | 0/1 | 4/4 | 2 | 20.0 | 20.6 | 12,732 / 360 | $0.0037 |
| ky-prefix-base-url | 1/1 | 1/1 | 2/2 | 2 | 7.7 | 8.6 | 13,791 / 306 | $0.0039 |
| ky-max-response-size | 0/1 | 0/1 | 3/3 | 2 | 12.9 | 13.9 | 11,562 / 312 | $0.0034 |

### Claude Sonnet 5, reranking on, run 1

| Metric | Value |
|---|---|
| Questions | 20 (2 errors) |
| Citation validity | 111/112 (99%) |
| Expected-file recall | 53% |
| Expected-symbol recall | 37% (18 questions) |
| Found nothing | 3/18 (17%) |
| Model latency | 15.6s mean |
| Run time | 21.2s mean |
| Tokens | 17,045 in / 1,697 out mean |
| Est. cost | $0.0511 mean, $0.9191 total |

| Question | Files | Symbols | Citations valid | Findings | Model s | Run s | Tokens in / out | Est. cost |
|---|---|---|---|---|---|---|---|---|
| typer-params-to-options | 1/2 | 1/2 | 10/10 | 8 | 16.8 | 24.3 | 13,082 / 1,968 | $0.0458 |
| typer-single-command | 0/1 | 0/1 | 0/0 | 0 | 3.3 | 7.9 | 10,502 / 199 | $0.0230 |
| typer-enum-choices | 1/1 | 1/2 | 7/7 | 4 | 11.4 | 17.2 | 9,444 / 1,098 | $0.0299 |
| typer-context-parameter | error | | | | | | | |
| typer-annotated | 0/1 | 0/1 | 7/7 | 5 | 13.0 | 18.6 | 19,426 / 1,268 | $0.0515 |
| typer-pretty-exceptions | 0/1 | 0/2 | 0/1 | 0 | 30.9 | 34.4 | 36,841 / 3,254 | $0.1062 |
| typer-rich-help | 2/2 | 1/1 | 7/7 | 7 | 38.0 | 45.4 | 36,907 / 4,368 | $0.1175 |
| typer-did-you-mean | 1/1 | 0/1 | 3/3 | 3 | 9.2 | 14.8 | 20,530 / 1,039 | $0.0514 |
| typer-install-completion | 1/1 | 2/3 | 5/5 | 5 | 13.1 | 18.2 | 5,153 / 1,064 | $0.0209 |
| typer-cli-runner | 1/1 | 1/2 | 8/8 | 8 | 22.1 | 28.5 | 11,236 / 2,673 | $0.0492 |
| typer-find-app | 0/1 | 0/1 | 0/0 | 0 | 3.2 | 7.5 | 7,033 / 280 | $0.0169 |
| ky-retry-decision | 1/2 | 1/1 | 9/9 | 9 | 16.2 | 21.6 | 19,907 / 1,791 | $0.0577 |
| ky-retry-after | 0/2 | 0/2 | 9/9 | 7 | 13.6 | 20.1 | 13,635 / 1,577 | $0.0430 |
| ky-retry-delay | 1/1 | 1/1 | 7/7 | 5 | 9.9 | 15.3 | 11,807 / 1,214 | $0.0358 |
| ky-timeout | 1/2 | 0/2 | 6/6 | 6 | 12.6 | 19.1 | 6,733 / 1,465 | $0.0281 |
| ky-before-request-hooks | 0/1 | 0/1 | 9/9 | 7 | 22.2 | 28.2 | 29,331 / 2,321 | $0.0819 |
| ky-extend | 2/2 | 1/2 | 10/10 | 7 | 13.1 | 18.6 | 10,578 / 1,510 | $0.0363 |
| ky-json-body | 0/1 | 0/1 | 8/8 | 8 | 17.1 | 22.6 | 31,946 / 2,055 | $0.0844 |
| ky-prefix-base-url | 1/1 | 1/1 | 6/6 | 6 | 14.5 | 19.2 | 12,720 / 1,402 | $0.0395 |
| ky-max-response-size | error | | | | | | | |

Errors:
- typer-context-parameter: claude-sonnet-5: the answer didn't fit the schema
- ky-max-response-size: claude-sonnet-5: the answer didn't fit the schema

### Claude Sonnet 5, reranking on, run 2

| Metric | Value |
|---|---|
| Questions | 20 (0 errors) |
| Citation validity | 131/131 (100%) |
| Expected-file recall | 50% |
| Expected-symbol recall | 36% (20 questions) |
| Found nothing | 1/20 (5%) |
| Model latency | 16.8s mean |
| Run time | 23.8s mean |
| Tokens | 19,652 in / 1,834 out mean |
| Est. cost | $0.0576 mean, $1.1529 total |

| Question | Files | Symbols | Citations valid | Findings | Model s | Run s | Tokens in / out | Est. cost |
|---|---|---|---|---|---|---|---|---|
| typer-params-to-options | 1/2 | 1/2 | 9/9 | 6 | 15.5 | 24.3 | 13,039 / 1,796 | $0.0440 |
| typer-single-command | 0/1 | 0/1 | 0/0 | 0 | 3.7 | 8.9 | 10,503 / 158 | $0.0226 |
| typer-enum-choices | 1/1 | 1/2 | 5/5 | 3 | 9.5 | 16.4 | 9,390 / 915 | $0.0279 |
| typer-context-parameter | 0/1 | 0/2 | 3/3 | 3 | 18.9 | 25.8 | 15,382 / 1,995 | $0.0507 |
| typer-annotated | 0/1 | 0/1 | 8/8 | 6 | 22.8 | 28.7 | 20,564 / 2,537 | $0.0665 |
| typer-pretty-exceptions | 1/1 | 2/2 | 6/6 | 6 | 18.4 | 26.0 | 12,964 / 2,321 | $0.0491 |
| typer-rich-help | 2/2 | 1/1 | 8/8 | 8 | 14.8 | 22.8 | 16,000 / 1,595 | $0.0479 |
| typer-did-you-mean | 1/1 | 0/1 | 3/3 | 2 | 13.3 | 21.1 | 30,657 / 997 | $0.0713 |
| typer-install-completion | 1/1 | 2/3 | 10/10 | 6 | 12.5 | 20.5 | 5,230 / 1,519 | $0.0256 |
| typer-cli-runner | 1/1 | 1/2 | 6/6 | 6 | 16.0 | 23.2 | 10,723 / 1,878 | $0.0402 |
| typer-find-app | 0/1 | 0/1 | 2/2 | 1 | 12.0 | 18.9 | 15,869 / 946 | $0.0412 |
| ky-retry-decision | 1/2 | 1/1 | 11/11 | 11 | 24.7 | 31.8 | 21,161 / 3,140 | $0.0737 |
| ky-retry-after | 0/2 | 0/2 | 18/18 | 10 | 19.6 | 24.8 | 13,741 / 2,237 | $0.0499 |
| ky-retry-delay | 1/1 | 1/1 | 7/7 | 5 | 9.5 | 16.6 | 11,807 / 1,140 | $0.0350 |
| ky-timeout | 1/2 | 0/2 | 5/5 | 5 | 14.0 | 21.6 | 6,682 / 1,332 | $0.0267 |
| ky-before-request-hooks | 0/1 | 0/1 | 9/9 | 8 | 43.2 | 50.1 | 62,846 / 4,956 | $0.1753 |
| ky-extend | 1/2 | 0/2 | 1/1 | 1 | 27.7 | 35.2 | 57,213 / 2,962 | $0.1440 |
| ky-json-body | 0/1 | 0/1 | 7/7 | 6 | 18.3 | 25.0 | 31,820 / 1,970 | $0.0833 |
| ky-prefix-base-url | 1/1 | 1/1 | 5/5 | 5 | 10.4 | 17.3 | 12,580 / 1,145 | $0.0366 |
| ky-max-response-size | 0/1 | 0/1 | 8/8 | 5 | 10.9 | 18.0 | 14,870 / 1,138 | $0.0411 |

### Claude Sonnet 5, reranking off, run 1

| Metric | Value |
|---|---|
| Questions | 20 (0 errors) |
| Citation validity | 143/148 (97%) |
| Expected-file recall | 50% |
| Expected-symbol recall | 45% (20 questions) |
| Found nothing | 0/20 (0%) |
| Model latency | 19.8s mean |
| Run time | 23.7s mean |
| Tokens | 29,960 in / 2,199 out mean |
| Est. cost | $0.0819 mean, $1.6383 total |

| Question | Files | Symbols | Citations valid | Findings | Model s | Run s | Tokens in / out | Est. cost |
|---|---|---|---|---|---|---|---|---|
| typer-params-to-options | 1/2 | 1/2 | 6/6 | 6 | 22.9 | 26.7 | 27,063 / 2,422 | $0.0783 |
| typer-single-command | 1/1 | 1/1 | 1/1 | 1 | 14.9 | 18.7 | 41,490 / 1,352 | $0.0965 |
| typer-enum-choices | 0/1 | 0/2 | 7/7 | 5 | 20.5 | 24.6 | 17,957 / 2,395 | $0.0599 |
| typer-context-parameter | 0/1 | 0/2 | 1/1 | 1 | 14.8 | 18.8 | 32,954 / 1,185 | $0.0778 |
| typer-annotated | 0/1 | 0/1 | 8/8 | 7 | 35.7 | 39.9 | 73,263 / 4,301 | $0.1895 |
| typer-pretty-exceptions | 1/1 | 2/2 | 7/7 | 7 | 20.3 | 24.1 | 14,390 / 2,441 | $0.0532 |
| typer-rich-help | 1/2 | 1/1 | 10/10 | 9 | 23.6 | 27.4 | 21,822 / 2,861 | $0.0723 |
| typer-did-you-mean | 1/1 | 0/1 | 3/3 | 2 | 21.3 | 25.1 | 29,447 / 1,334 | $0.0722 |
| typer-install-completion | 1/1 | 3/3 | 6/6 | 6 | 19.5 | 23.2 | 12,638 / 2,451 | $0.0498 |
| typer-cli-runner | 1/1 | 1/2 | 9/9 | 6 | 20.7 | 24.4 | 9,761 / 2,432 | $0.0438 |
| typer-find-app | 1/1 | 1/1 | 8/8 | 6 | 15.0 | 18.9 | 10,933 / 1,778 | $0.0396 |
| ky-retry-decision | 1/2 | 1/1 | 13/13 | 13 | 17.4 | 20.5 | 12,725 / 2,191 | $0.0474 |
| ky-retry-after | 0/2 | 0/2 | 18/18 | 14 | 19.5 | 23.3 | 31,741 / 2,361 | $0.0871 |
| ky-retry-delay | 0/1 | 0/1 | 11/11 | 9 | 24.0 | 27.6 | 30,113 / 3,128 | $0.0915 |
| ky-timeout | 1/2 | 0/2 | 5/5 | 5 | 15.4 | 19.5 | 32,125 / 1,619 | $0.0804 |
| ky-before-request-hooks | 0/1 | 0/1 | 9/9 | 9 | 13.5 | 17.6 | 14,922 / 1,627 | $0.0461 |
| ky-extend | 0/2 | 0/2 | 5/10 | 3 | 16.0 | 20.5 | 29,798 / 1,619 | $0.0758 |
| ky-json-body | 1/1 | 1/1 | 6/6 | 6 | 12.7 | 17.0 | 32,345 / 1,073 | $0.0754 |
| ky-prefix-base-url | 1/1 | 1/1 | 4/4 | 4 | 29.4 | 33.8 | 92,729 / 3,406 | $0.2195 |
| ky-max-response-size | 0/1 | 0/1 | 6/6 | 5 | 18.1 | 22.1 | 30,986 / 2,012 | $0.0821 |

### Claude Sonnet 5, reranking off, run 2

| Metric | Value |
|---|---|
| Questions | 20 (3 errors) |
| Citation validity | 115/115 (100%) |
| Expected-file recall | 53% |
| Expected-symbol recall | 44% (17 questions) |
| Found nothing | 1/17 (6%) |
| Model latency | 21.4s mean |
| Run time | 26.9s mean |
| Tokens | 31,484 in / 2,311 out mean |
| Est. cost | $0.0861 mean, $1.4634 total |

| Question | Files | Symbols | Citations valid | Findings | Model s | Run s | Tokens in / out | Est. cost |
|---|---|---|---|---|---|---|---|---|
| typer-params-to-options | 1/2 | 1/2 | 8/8 | 7 | 19.5 | 25.3 | 26,330 / 1,879 | $0.0714 |
| typer-single-command | 1/1 | 1/1 | 2/2 | 2 | 9.3 | 15.0 | 20,322 / 844 | $0.0491 |
| typer-enum-choices | 1/1 | 0/2 | 7/7 | 5 | 16.1 | 21.3 | 17,098 / 1,483 | $0.0490 |
| typer-context-parameter | 0/1 | 0/2 | 0/0 | 0 | 4.5 | 8.6 | 7,295 / 241 | $0.0170 |
| typer-annotated | 0/1 | 0/1 | 9/9 | 6 | 38.3 | 43.9 | 74,101 / 4,822 | $0.1964 |
| typer-pretty-exceptions | 1/1 | 2/2 | 6/6 | 6 | 24.2 | 29.6 | 14,216 / 2,184 | $0.0503 |
| typer-rich-help | 1/2 | 1/1 | 9/9 | 8 | 16.2 | 21.8 | 10,649 / 1,815 | $0.0394 |
| typer-did-you-mean | 1/1 | 0/1 | 3/3 | 2 | 13.0 | 18.5 | 19,408 / 900 | $0.0478 |
| typer-install-completion | error | | | | | | | |
| typer-cli-runner | error | | | | | | | |
| typer-find-app | 1/1 | 1/1 | 8/8 | 8 | 19.7 | 25.7 | 11,312 / 2,327 | $0.0459 |
| ky-retry-decision | 1/2 | 1/1 | 13/13 | 9 | 16.4 | 22.4 | 12,569 / 1,972 | $0.0449 |
| ky-retry-after | 0/2 | 0/2 | 14/14 | 11 | 37.9 | 41.7 | 50,969 / 4,538 | $0.1473 |
| ky-retry-delay | error | | | | | | | |
| ky-timeout | 1/2 | 0/2 | 5/5 | 5 | 21.7 | 26.7 | 49,467 / 2,529 | $0.1242 |
| ky-before-request-hooks | 0/1 | 0/1 | 11/11 | 11 | 16.3 | 21.6 | 15,013 / 1,833 | $0.0484 |
| ky-extend | 0/2 | 0/2 | 8/8 | 6 | 20.5 | 25.9 | 30,990 / 2,444 | $0.0864 |
| ky-json-body | 1/1 | 1/1 | 4/4 | 4 | 8.2 | 15.0 | 16,350 / 902 | $0.0417 |
| ky-prefix-base-url | 1/1 | 1/1 | 7/7 | 7 | 47.4 | 53.1 | 76,085 / 4,905 | $0.2012 |
| ky-max-response-size | 0/1 | 0/1 | 1/1 | 1 | 35.3 | 40.6 | 83,062 / 3,671 | $0.2028 |

Errors:
- typer-install-completion: claude-sonnet-5: the answer didn't fit the schema
- typer-cli-runner: claude-sonnet-5 timed out (120s)
- ky-retry-delay: claude-sonnet-5: the answer didn't fit the schema
