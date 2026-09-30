# Agent vs one-shot Code Navigator

Recorded 2026-09-30 with `repolens eval` on [`evals/questions.toml`](../questions.toml), the same 20 questions as the [baseline](baseline.md): 11 on `fastapi/typer@a80f6e5` and 9 on `sindresorhus/ky@0d59458`. Reranking on.

- **Agent** (`--steps 8`): the Run searches for the question, then the model takes up to 8 Agent steps. Each step either calls a Tool (`search`, `read`, `define`) or answers.
- **One-shot** (`--steps 1`): the same first search, then the model must answer at once.

This is the second recording. Since the first one:
- a search shows the first lines of every hit, instead of cutting the result at 500 lines;
- the prompt asks the agent to answer only once it has seen the code that does the work, not tests or type declarations that mention it;
- a Gemini rate limit (429) is retried once after the delay it asks for.

## Summary

Each metric is over the questions that got an answer. Errors are counted separately.

| Setup | Runs | File recall | Symbol recall | Found nothing | Citation validity | Input tokens | Run time | Est. cost | Errors |
|---|---|---|---|---|---|---|---|---|---|
| Gemini 3.1 Flash-Lite, one-shot | 2 | 58–64% | 38–43% | 0% | 100% | 5,735 | 12.5s | $0.0020 | 3 / 40 |
| Gemini 3.1 Flash-Lite, agent | 2 | 66–71% | 54–59% | 0% | 96–100% | 9,926 | 15.4s | $0.0031 | 2 / 40 |
| Claude Sonnet 5, one-shot | 2 | 52% | 38% | 10% | 99–100% | 8,184 | 16.8s | $0.0265 | 0 / 40 |
| Claude Sonnet 5, agent | 2 | 85–92% | 88–93% | 0% | 99% | 29,050 | 27.7s | $0.0707 | 0 / 40 |

Ranges are the two runs. Tokens, run time and cost are the mean per question over both runs. The five Gemini errors are 503s (the model was overloaded); no Run hit a 429 this time.

Against the first recording:

| Setup | File recall | Symbol recall | Input tokens |
|---|---|---|---|
| Gemini 3.1 Flash-Lite, one-shot | 55–57% → 58–64% | 37–38% → 38–43% | 5,790 → 5,735 |
| Gemini 3.1 Flash-Lite, agent | 61–62% → 66–71% | 48–51% → 54–59% | 8,918 → 9,926 |
| Claude Sonnet 5, one-shot | 55–60% → 52% | 38% → 38% | 8,125 → 8,184 |
| Claude Sonnet 5, agent | 85–88% → 85–92% | 83–86% → 88–93% | 23,462 → 29,050 |

## What it says

- **Every first search now shows all 6 hits**, in every Run. Before, about 60% were cut at 500 lines. Long hits show their first ~80 lines.
- **Gemini 3.1 Flash-Lite still answers from the first search.** It answered at step 1 in 25 of its 38 agent Runs (27 of 39 before), so the new prompt barely changed its behaviour. Its agent gains one question in both runs, `typer-find-app`. The rest of the rise, and all of the one-shot rise, comes from errors landing on questions it partly or fully misses: its one-shot answers are the same per question as before.
- **Claude Sonnet 5 gains a little more.** Symbol recall goes from 83–86% to 88–93%, and `ky-before-request-hooks` is answered in one run. Input tokens go up by a quarter, from the two ky questions below: Sonnet 5 kept searching on them until a limit, at 108k–188k tokens per Run.
- **Sonnet 5 one-shot loses a little.** With long hits cut to their first lines, it sees less of the top hits. It misses `typer-single-command` in both runs and half of `typer-params-to-options`. The agent reads the rest, so this doesn't carry over.
- **Citations stay valid.** The verifier kept 96–100% of Citations in every setup.

## Why `ky-before-request-hooks` and `ky-json-body` are missed

The dataset is right: `Ky.#runBeforeRequestHooks` (source/core/Ky.ts:1003) runs the hooks and takes a returned `Request` or `Response`, and `Ky.constructor` (Ky.ts:456) turns `json` into the body and sets `content-type`. Retrieval rarely gets there:

- ky's tests are long files (`test/hooks.ts` has about 6,500 lines, in 150-line Chunks) that use every option by name, and `source/types/*.ts` documents every option in JSDoc. For both questions, hybrid search fills all 24 candidates with tests and type declarations. `#runBeforeRequestHooks` isn't a candidate at all, and `Ky.constructor` is 18th of 24 after reranking.
- A short query finds the code: `run beforeRequest hooks` ranks `Ky.#runBeforeRequestHooks` second. Sonnet 5 got there once. On `ky-json-body`, every follow-up search it made returned more tests, until the Run's 1,500-line limit.

The fix belongs in retrieval, e.g. ranking test files below source files, or a Tool that lists a directory. It's left for a later change.

## How the agent used its steps

| Model | Runs | Agent steps per Run | Tool calls |
|---|---|---|---|
| Claude Sonnet 5 | 40 | 1: 10, 2: 21, 3: 5, 4: 1, 5: 1, 8: 2 | 43 search, 7 read, 2 define |
| Gemini 3.1 Flash-Lite | 38 | 1: 25, 2: 11, 5: 2 | 13 search, 3 read, 3 define |

Only the two ky questions above hit a limit: 2 Sonnet 5 Runs reached the 8-step limit, and 3 the 1,500-line limit per Run.

## Expected-file recall per question

Both runs of each setup.

| Question | Gemini one-shot | Gemini agent | Sonnet one-shot | Sonnet agent |
|---|---|---|---|---|
| typer-params-to-options | 1/2, error | 1/2, 1/2 | 1/2, 1/2 | 2/2, 2/2 |
| typer-single-command | 1/1, 1/1 | 1/1, 1/1 | 0/1, 0/1 | 1/1, 1/1 |
| typer-enum-choices | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 |
| typer-context-parameter | 0/1, 0/1 | 0/1, 0/1 | 0/1, 0/1 | 1/1, 1/1 |
| typer-annotated | error, 0/1 | 0/1, 0/1 | 0/1, 0/1 | 1/1, 1/1 |
| typer-pretty-exceptions | 1/1, 1/1 | 1/1, error | 1/1, 1/1 | 1/1, 1/1 |
| typer-rich-help | 2/2, 2/2 | 2/2, 2/2 | 2/2, 2/2 | 2/2, 2/2 |
| typer-did-you-mean | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 |
| typer-install-completion | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 |
| typer-cli-runner | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 |
| typer-find-app | 0/1, 0/1 | 1/1, 1/1 | 0/1, 0/1 | 1/1, 1/1 |
| ky-retry-decision | 1/2, 1/2 | 1/2, 1/2 | 1/2, 1/2 | 1/2, 1/2 |
| ky-retry-after | 0/2, 0/2 | error, 0/2 | 0/2, 0/2 | 2/2, 1/2 |
| ky-retry-delay | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 |
| ky-timeout | 1/2, 1/2 | 1/2, 1/2 | 1/2, 1/2 | 2/2, 2/2 |
| ky-before-request-hooks | 0/1, 0/1 | 0/1, 0/1 | 0/1, 0/1 | 1/1, 0/1 |
| ky-extend | 2/2, 2/2 | 2/2, 2/2 | 2/2, 2/2 | 2/2, 2/2 |
| ky-json-body | 0/1, 0/1 | 0/1, 0/1 | 0/1, 0/1 | 0/1, 0/1 |
| ky-prefix-base-url | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 |
| ky-max-response-size | error, 0/1 | 1/1, 1/1 | 0/1, 0/1 | 1/1, 1/1 |

## Per-question results, run 1

### Gemini 3.1 Flash-Lite, agent

| Question | Files | Symbols | Citations valid | Findings | Model s | Run s | Tokens in / out | Est. cost |
| typer-params-to-options | 1/2 | 1/2 | 4/4 | 3 | 12.0 | 14.8 | 6,708 / 499 | $0.0024 |
| typer-single-command | 1/1 | 0/1 | 2/2 | 1 | 8.3 | 11.3 | 6,066 / 231 | $0.0019 |
| typer-enum-choices | 1/1 | 1/2 | 4/4 | 3 | 6.8 | 9.6 | 2,785 / 483 | $0.0014 |
| typer-context-parameter | 0/1 | 0/2 | 2/2 | 1 | 20.1 | 27.7 | 7,809 / 252 | $0.0023 |
| typer-annotated | 0/1 | 0/1 | 3/3 | 2 | 9.5 | 12.8 | 6,749 / 426 | $0.0023 |
| typer-pretty-exceptions | 1/1 | 2/2 | 4/4 | 3 | 5.9 | 9.2 | 3,946 / 480 | $0.0017 |
| typer-rich-help | 2/2 | 1/1 | 4/4 | 3 | 5.0 | 7.6 | 5,821 / 492 | $0.0022 |
| typer-did-you-mean | 1/1 | 1/1 | 2/2 | 2 | 23.9 | 29.5 | 13,778 / 334 | $0.0039 |
| typer-install-completion | 1/1 | 2/3 | 4/4 | 2 | 4.9 | 7.7 | 3,095 / 454 | $0.0015 |
| typer-cli-runner | 1/1 | 2/2 | 3/3 | 2 | 9.4 | 11.8 | 7,681 / 401 | $0.0025 |
| typer-find-app | 1/1 | 1/1 | 4/4 | 3 | 15.8 | 23.7 | 37,494 / 649 | $0.0103 |
| ky-retry-decision | 1/2 | 1/1 | 7/7 | 2 | 12.3 | 14.7 | 7,034 / 596 | $0.0027 |
| ky-retry-after | error | | | | | | | |
| ky-retry-delay | 1/1 | 1/1 | 7/7 | 4 | 8.8 | 11.8 | 7,165 / 695 | $0.0028 |
| ky-timeout | 1/2 | 0/2 | 3/3 | 3 | 11.0 | 16.6 | 15,720 / 398 | $0.0045 |
| ky-before-request-hooks | 0/1 | 0/1 | 3/3 | 3 | 8.7 | 11.6 | 7,433 / 385 | $0.0024 |
| ky-extend | 2/2 | 1/2 | 2/2 | 2 | 4.8 | 8.2 | 7,168 / 307 | $0.0023 |
| ky-json-body | 0/1 | 0/1 | 2/2 | 1 | 9.5 | 13.0 | 7,297 / 246 | $0.0022 |
| ky-prefix-base-url | 1/1 | 1/1 | 2/2 | 2 | 10.3 | 12.8 | 7,677 / 314 | $0.0024 |
| ky-max-response-size | 1/1 | 1/1 | 3/3 | 3 | 19.1 | 31.3 | 18,977 / 416 | $0.0054 |

### Gemini 3.1 Flash-Lite, one-shot

| Question | Files | Symbols | Citations valid | Findings | Model s | Run s | Tokens in / out | Est. cost |
| typer-params-to-options | 1/2 | 1/2 | 5/5 | 2 | 12.7 | 17.0 | 6,678 / 471 | $0.0024 |
| typer-single-command | 1/1 | 0/1 | 2/2 | 1 | 5.7 | 8.7 | 6,070 / 228 | $0.0019 |
| typer-enum-choices | 1/1 | 1/2 | 3/3 | 3 | 15.8 | 18.7 | 2,798 / 433 | $0.0013 |
| typer-context-parameter | 0/1 | 0/2 | 2/2 | 1 | 5.9 | 8.6 | 2,920 / 218 | $0.0011 |
| typer-annotated | error | | | | | | | |
| typer-pretty-exceptions | 1/1 | 2/2 | 6/6 | 3 | 9.0 | 12.9 | 3,949 / 567 | $0.0018 |
| typer-rich-help | 2/2 | 1/1 | 4/4 | 3 | 6.1 | 8.4 | 5,820 / 488 | $0.0022 |
| typer-did-you-mean | 1/1 | 0/1 | 2/2 | 1 | 10.4 | 13.4 | 6,303 / 240 | $0.0019 |
| typer-install-completion | 1/1 | 2/3 | 2/2 | 2 | 9.1 | 11.2 | 3,105 / 343 | $0.0013 |
| typer-cli-runner | 1/1 | 1/2 | 2/2 | 1 | 5.6 | 7.8 | 3,099 / 225 | $0.0011 |
| typer-find-app | 0/1 | 0/1 | 3/3 | 2 | 10.7 | 12.9 | 5,993 / 410 | $0.0021 |
| ky-retry-decision | 1/2 | 1/1 | 8/8 | 4 | 6.7 | 9.6 | 7,102 / 726 | $0.0029 |
| ky-retry-after | 0/2 | 0/2 | 6/6 | 3 | 16.8 | 19.3 | 7,226 / 492 | $0.0025 |
| ky-retry-delay | 1/1 | 1/1 | 4/4 | 3 | 7.7 | 10.4 | 7,161 / 527 | $0.0026 |
| ky-timeout | 1/2 | 0/2 | 5/5 | 2 | 13.4 | 17.8 | 4,331 / 447 | $0.0018 |
| ky-before-request-hooks | 0/1 | 0/1 | 3/3 | 3 | 8.4 | 11.6 | 7,437 / 377 | $0.0024 |
| ky-extend | 2/2 | 1/2 | 3/3 | 2 | 4.8 | 7.3 | 7,172 / 330 | $0.0023 |
| ky-json-body | 0/1 | 0/1 | 3/3 | 2 | 6.1 | 8.9 | 7,328 / 343 | $0.0023 |
| ky-prefix-base-url | 1/1 | 1/1 | 2/2 | 2 | 9.5 | 12.6 | 7,676 / 297 | $0.0024 |
| ky-max-response-size | error | | | | | | | |

### Claude Sonnet 5, agent

| Question | Files | Symbols | Citations valid | Findings | Model s | Run s | Tokens in / out | Est. cost |
| typer-params-to-options | 2/2 | 2/2 | 4/5 | 4 | 14.5 | 25.0 | 22,478 / 1,371 | $0.0587 |
| typer-single-command | 1/1 | 1/1 | 1/1 | 1 | 7.9 | 19.2 | 20,126 / 534 | $0.0456 |
| typer-enum-choices | 1/1 | 2/2 | 8/8 | 5 | 17.3 | 32.9 | 23,372 / 1,566 | $0.0624 |
| typer-context-parameter | 1/1 | 2/2 | 5/5 | 5 | 14.7 | 31.0 | 23,149 / 1,208 | $0.0584 |
| typer-annotated | 1/1 | 1/1 | 10/10 | 7 | 20.5 | 31.8 | 24,300 / 2,180 | $0.0704 |
| typer-pretty-exceptions | 1/1 | 2/2 | 5/5 | 5 | 12.3 | 20.8 | 6,791 / 1,300 | $0.0266 |
| typer-rich-help | 2/2 | 1/1 | 5/5 | 5 | 14.3 | 40.5 | 21,515 / 1,177 | $0.0548 |
| typer-did-you-mean | 1/1 | 1/1 | 4/4 | 3 | 11.7 | 28.1 | 19,745 / 949 | $0.0490 |
| typer-install-completion | 1/1 | 2/3 | 5/5 | 4 | 8.8 | 18.4 | 5,562 / 942 | $0.0205 |
| typer-cli-runner | 1/1 | 2/2 | 9/9 | 5 | 15.5 | 26.4 | 14,434 / 1,559 | $0.0445 |
| typer-find-app | 1/1 | 1/1 | 4/4 | 4 | 11.8 | 22.5 | 17,875 / 1,103 | $0.0468 |
| ky-retry-decision | 1/2 | 1/1 | 6/6 | 6 | 11.2 | 17.2 | 9,942 / 1,290 | $0.0328 |
| ky-retry-after | 2/2 | 2/2 | 4/4 | 3 | 12.1 | 24.5 | 24,488 / 1,169 | $0.0607 |
| ky-retry-delay | 1/1 | 1/1 | 5/5 | 4 | 8.0 | 14.0 | 9,626 / 891 | $0.0282 |
| ky-timeout | 2/2 | 2/2 | 5/5 | 5 | 14.6 | 26.9 | 20,449 / 1,368 | $0.0546 |
| ky-before-request-hooks | 1/1 | 1/1 | 4/4 | 4 | 12.4 | 29.0 | 44,259 / 1,201 | $0.1005 |
| ky-extend | 2/2 | 2/2 | 3/3 | 3 | 9.0 | 17.9 | 18,709 / 799 | $0.0454 |
| ky-json-body | 0/1 | 0/1 | 7/7 | 7 | 41.5 | 89.4 | 188,050 / 2,021 | $0.3963 |
| ky-prefix-base-url | 1/1 | 1/1 | 2/2 | 2 | 7.3 | 14.6 | 10,957 / 609 | $0.0280 |
| ky-max-response-size | 1/1 | 1/1 | 5/5 | 3 | 10.1 | 22.2 | 27,872 / 1,020 | $0.0659 |

### Claude Sonnet 5, one-shot

| Question | Files | Symbols | Citations valid | Findings | Model s | Run s | Tokens in / out | Est. cost |
| typer-params-to-options | 1/2 | 1/2 | 7/7 | 6 | 13.9 | 21.7 | 9,243 / 1,554 | $0.0340 |
| typer-single-command | 0/1 | 0/1 | 0/0 | 0 | 4.6 | 9.5 | 7,348 / 364 | $0.0183 |
| typer-enum-choices | 1/1 | 1/2 | 3/3 | 3 | 8.4 | 14.2 | 5,026 / 741 | $0.0175 |
| typer-context-parameter | 0/1 | 0/2 | 3/3 | 3 | 9.7 | 15.9 | 4,950 / 790 | $0.0178 |
| typer-annotated | 0/1 | 0/1 | 8/8 | 5 | 14.1 | 20.8 | 9,321 / 1,624 | $0.0349 |
| typer-pretty-exceptions | 1/1 | 2/2 | 5/5 | 5 | 12.4 | 18.4 | 6,536 / 1,262 | $0.0257 |
| typer-rich-help | 2/2 | 1/1 | 8/8 | 6 | 12.5 | 17.9 | 8,491 / 1,495 | $0.0319 |
| typer-did-you-mean | 1/1 | 0/1 | 2/2 | 1 | 5.2 | 11.4 | 8,488 / 395 | $0.0209 |
| typer-install-completion | 1/1 | 2/3 | 7/7 | 5 | 11.5 | 18.5 | 5,394 / 1,219 | $0.0230 |
| typer-cli-runner | 1/1 | 1/2 | 5/5 | 4 | 14.5 | 20.4 | 5,420 / 1,151 | $0.0224 |
| typer-find-app | 0/1 | 0/1 | 0/0 | 0 | 5.3 | 11.2 | 7,209 / 446 | $0.0189 |
| ky-retry-decision | 1/2 | 1/1 | 8/8 | 8 | 13.7 | 19.7 | 9,815 / 1,594 | $0.0356 |
| ky-retry-after | 0/2 | 0/2 | 6/6 | 3 | 7.3 | 13.3 | 9,383 / 799 | $0.0268 |
| ky-retry-delay | 1/1 | 1/1 | 5/5 | 5 | 11.5 | 18.1 | 9,497 / 1,186 | $0.0309 |
| ky-timeout | 1/2 | 0/2 | 5/5 | 4 | 10.1 | 16.0 | 6,737 / 1,095 | $0.0244 |
| ky-before-request-hooks | 0/1 | 0/1 | 8/8 | 6 | 13.1 | 19.5 | 9,894 / 1,399 | $0.0338 |
| ky-extend | 2/2 | 1/2 | 3/3 | 3 | 10.6 | 17.9 | 9,537 / 852 | $0.0276 |
| ky-json-body | 0/1 | 0/1 | 6/6 | 6 | 10.9 | 19.3 | 10,128 / 1,082 | $0.0311 |
| ky-prefix-base-url | 1/1 | 1/1 | 3/3 | 3 | 8.2 | 14.7 | 10,798 / 841 | $0.0300 |
| ky-max-response-size | 0/1 | 0/1 | 3/3 | 3 | 10.7 | 16.8 | 10,872 / 876 | $0.0305 |
