# Agent vs one-shot Code Navigator

Recorded 2026-09-30 with `repolens eval` on [`evals/questions.toml`](../questions.toml), the same 20 questions as the [baseline](baseline.md): 11 on `fastapi/typer@a80f6e5` and 9 on `sindresorhus/ky@0d59458`. Reranking on.

- **Agent** (`--steps 8`): the Run searches for the question, then the model takes up to 8 Agent steps. Each step either calls a Tool (`search`, `read`, `define`) or answers.
- **One-shot** (`--steps 1`): the same first search, then the model must answer at once. This is the baseline's setup with the agent's prompt, and it scores about the same as the baseline.

## Summary

Each metric is over the questions that got an answer. Errors are counted separately.

| Setup | Runs | File recall | Symbol recall | Found nothing | Citation validity | Input tokens | Run time | Est. cost | Errors |
|---|---|---|---|---|---|---|---|---|---|
| Gemini 3.1 Flash-Lite, one-shot | 2 | 55–57% | 37–38% | 0% | 100% | 5,790 | 9.2s | $0.0021 | 1 / 40 |
| Gemini 3.1 Flash-Lite, agent | 2 | 61–62% | 48–51% | 0% | 100% | 8,918 | 9.5s | $0.0030 | 1 / 40 |
| Claude Sonnet 5, one-shot | 2 | 55–60% | 38% | 5–10% | 99–100% | 8,125 | 17.1s | $0.0273 | 0 / 40 |
| Claude Sonnet 5, agent | 2 | 85–88% | 83–86% | 0% | 99–100% | 23,462 | 25.5s | $0.0605 | 0 / 40 |

Ranges are the two runs. Tokens, run time and cost are the mean per question over both runs. The two Gemini errors are free-tier rate limits (429), one per run.

## What it says

- **On Claude Sonnet 5, the agent fixes retrieval.** File recall goes from 55–60% to 85–88%, and symbol recall from 38% to 83–86%. Six questions that every one-shot setup missed are now answered: `typer-context-parameter`, `typer-annotated`, `typer-find-app`, `ky-retry-after`, `ky-timeout` (second file) and `ky-max-response-size`. It costs about 3x the input tokens and 8s more per question.
- **Gemini 3.1 Flash-Lite gains a little.** File recall goes up about 5 points (one question, `ky-max-response-size`) and symbol recall about 12. It answers after the first search in 27 of its 39 Runs, so it rarely uses the Tools.
- **Citations stay valid.** The verifier kept 99–100% of Citations in every setup, including those to lines the agent read with a Tool.
- **Still missed by every setup:** `ky-before-request-hooks` and `ky-json-body`.

## How the agent used its steps

| Model | Runs | Agent steps per Run | Tool calls |
|---|---|---|---|
| Claude Sonnet 5 | 40 | 1: 14, 2: 15, 3: 8, 4: 2, 6: 1 | 39 search, 3 read, 0 define |
| Gemini 3.1 Flash-Lite | 39 | 1: 27, 2: 10, 3: 1, 4: 1 | 12 search, 1 read, 2 define |

No Run reached the 8-step limit. The line limits did bind:
- The first search was cut at 500 lines per Tool result in about 60% of Runs, for both models. Six Chunks of up to 150 lines often go past it.
- 2 Sonnet agent Runs reached the 1,500-line limit per Run.

Because of the cut, the one-shot setup uses fewer input tokens than the baseline did (Sonnet 5: 8,125 vs 18,349). Its file recall is about the same.

## Expected-file recall per question

Both runs of each setup.

| Question | Gemini one-shot | Gemini agent | Sonnet one-shot | Sonnet agent |
|---|---|---|---|---|
| typer-params-to-options | 1/2, 1/2 | 1/2, 1/2 | 2/2, 2/2 | 2/2, 2/2 |
| typer-single-command | 1/1, 1/1 | 1/1, 1/1 | 0/1, 1/1 | 1/1, 1/1 |
| typer-enum-choices | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 |
| typer-context-parameter | 0/1, 0/1 | 0/1, 0/1 | 0/1, 0/1 | 1/1, 1/1 |
| typer-annotated | 0/1, 0/1 | 0/1, 0/1 | 0/1, 0/1 | 1/1, 1/1 |
| typer-pretty-exceptions | 1/1, 1/1 | 1/1, error | 1/1, 1/1 | 1/1, 1/1 |
| typer-rich-help | 2/2, 2/2 | 2/2, 2/2 | 2/2, 2/2 | 2/2, 2/2 |
| typer-did-you-mean | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 |
| typer-install-completion | 1/1, error | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 |
| typer-cli-runner | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 |
| typer-find-app | 0/1, 0/1 | 0/1, 0/1 | 0/1, 0/1 | 1/1, 1/1 |
| ky-retry-decision | 1/2, 1/2 | 1/2, 1/2 | 1/2, 1/2 | 1/2, 1/2 |
| ky-retry-after | 0/2, 0/2 | 0/2, 0/2 | 0/2, 0/2 | 2/2, 1/2 |
| ky-retry-delay | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 |
| ky-timeout | 1/2, 1/2 | 1/2, 1/2 | 1/2, 1/2 | 2/2, 2/2 |
| ky-before-request-hooks | 0/1, 0/1 | 0/1, 0/1 | 0/1, 0/1 | 0/1, 0/1 |
| ky-extend | 2/2, 2/2 | 2/2, 2/2 | 2/2, 2/2 | 2/2, 2/2 |
| ky-json-body | 0/1, 0/1 | 0/1, 0/1 | 0/1, 0/1 | 0/1, 0/1 |
| ky-prefix-base-url | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 | 1/1, 1/1 |
| ky-max-response-size | 0/1, 0/1 | 1/1, 1/1 | 0/1, 0/1 | 1/1, 1/1 |

## Per-question results, run 1

### Gemini 3.1 Flash-Lite, agent

| Question | Files | Symbols | Citations valid | Findings | Model s | Run s | Tokens in / out | Est. cost |
|---|---|---|---|---|---|---|---|---|
| typer-params-to-options | 1/2 | 1/2 | 3/3 | 3 | 6.3 | 10.8 | 6,185 / 427 | $0.0022 |
| typer-single-command | 1/1 | 0/1 | 3/3 | 1 | 12.8 | 18.5 | 12,918 / 325 | $0.0037 |
| typer-enum-choices | 1/1 | 1/2 | 4/4 | 3 | 4.8 | 7.9 | 2,725 / 474 | $0.0014 |
| typer-context-parameter | 0/1 | 0/2 | 2/2 | 2 | 5.2 | 10.5 | 7,750 / 330 | $0.0024 |
| typer-annotated | 0/1 | 0/1 | 4/4 | 2 | 7.6 | 10.0 | 6,498 / 508 | $0.0024 |
| typer-pretty-exceptions | 1/1 | 2/2 | 4/4 | 4 | 5.0 | 7.4 | 3,927 / 528 | $0.0018 |
| typer-rich-help | 2/2 | 1/1 | 5/5 | 3 | 3.4 | 5.8 | 5,759 / 561 | $0.0023 |
| typer-did-you-mean | 1/1 | 1/1 | 4/4 | 3 | 14.7 | 22.2 | 31,799 / 576 | $0.0088 |
| typer-install-completion | 1/1 | 2/3 | 2/2 | 2 | 7.0 | 9.8 | 3,027 / 317 | $0.0012 |
| typer-cli-runner | 1/1 | 2/2 | 3/3 | 2 | 13.0 | 16.3 | 7,567 / 394 | $0.0025 |
| typer-find-app | 0/1 | 0/1 | 2/2 | 2 | 8.0 | 10.5 | 5,917 / 350 | $0.0020 |
| ky-retry-decision | 1/2 | 1/1 | 8/8 | 3 | 5.5 | 8.0 | 6,941 / 700 | $0.0028 |
| ky-retry-after | 0/2 | 0/2 | 7/7 | 3 | 10.9 | 15.9 | 20,329 / 562 | $0.0059 |
| ky-retry-delay | 1/1 | 1/1 | 6/6 | 4 | 4.2 | 6.8 | 7,013 / 641 | $0.0027 |
| ky-timeout | 1/2 | 0/2 | 7/7 | 3 | 8.1 | 11.4 | 4,271 / 589 | $0.0020 |
| ky-before-request-hooks | 0/1 | 0/1 | 4/4 | 3 | 6.8 | 9.4 | 7,078 / 436 | $0.0024 |
| ky-extend | 2/2 | 1/2 | 5/5 | 3 | 8.9 | 12.5 | 6,986 / 478 | $0.0025 |
| ky-json-body | 0/1 | 0/1 | 5/5 | 5 | 6.7 | 9.2 | 8,124 / 563 | $0.0029 |
| ky-prefix-base-url | 1/1 | 1/1 | 2/2 | 2 | 5.7 | 9.1 | 7,556 / 286 | $0.0023 |
| ky-max-response-size | 1/1 | 1/1 | 3/3 | 2 | 7.3 | 13.7 | 17,628 / 379 | $0.0050 |

### Gemini 3.1 Flash-Lite, one-shot

| Question | Files | Symbols | Citations valid | Findings | Model s | Run s | Tokens in / out | Est. cost |
|---|---|---|---|---|---|---|---|---|
| typer-params-to-options | 1/2 | 1/2 | 3/3 | 3 | 10.6 | 13.5 | 6,199 / 434 | $0.0022 |
| typer-single-command | 1/1 | 0/1 | 1/1 | 1 | 4.8 | 7.9 | 5,777 / 173 | $0.0017 |
| typer-enum-choices | 1/1 | 1/2 | 4/4 | 3 | 11.7 | 15.7 | 2,734 / 464 | $0.0014 |
| typer-context-parameter | 0/1 | 0/2 | 2/2 | 1 | 9.2 | 11.8 | 2,874 / 224 | $0.0011 |
| typer-annotated | 0/1 | 0/1 | 6/6 | 2 | 5.8 | 8.4 | 6,490 / 530 | $0.0024 |
| typer-pretty-exceptions | 1/1 | 2/2 | 4/4 | 3 | 8.3 | 10.4 | 3,895 / 468 | $0.0017 |
| typer-rich-help | 2/2 | 1/1 | 4/4 | 4 | 11.1 | 13.5 | 5,798 / 559 | $0.0023 |
| typer-did-you-mean | 1/1 | 0/1 | 2/2 | 2 | 11.1 | 14.4 | 6,142 / 296 | $0.0020 |
| typer-install-completion | 1/1 | 2/3 | 2/2 | 2 | 7.3 | 11.2 | 3,036 / 331 | $0.0013 |
| typer-cli-runner | 1/1 | 1/2 | 2/2 | 2 | 7.8 | 10.0 | 3,067 / 276 | $0.0012 |
| typer-find-app | 0/1 | 0/1 | 2/2 | 2 | 6.6 | 10.0 | 5,913 / 326 | $0.0020 |
| ky-retry-decision | 1/2 | 1/1 | 9/9 | 4 | 15.0 | 17.5 | 6,983 / 820 | $0.0030 |
| ky-retry-after | 0/2 | 0/2 | 7/7 | 4 | 10.4 | 12.8 | 7,036 / 597 | $0.0027 |
| ky-retry-delay | 1/1 | 1/1 | 6/6 | 4 | 6.4 | 8.9 | 6,996 / 621 | $0.0027 |
| ky-timeout | 1/2 | 0/2 | 4/4 | 2 | 9.2 | 11.5 | 4,273 / 399 | $0.0017 |
| ky-before-request-hooks | 0/1 | 0/1 | 4/4 | 3 | 3.2 | 5.7 | 7,081 / 426 | $0.0024 |
| ky-extend | 2/2 | 1/2 | 3/3 | 3 | 3.3 | 5.9 | 7,010 / 417 | $0.0024 |
| ky-json-body | 0/1 | 0/1 | 4/4 | 3 | 3.1 | 5.5 | 8,091 / 424 | $0.0027 |
| ky-prefix-base-url | 1/1 | 1/1 | 2/2 | 2 | 2.8 | 5.2 | 7,572 / 306 | $0.0024 |
| ky-max-response-size | 0/1 | 0/1 | 5/5 | 2 | 3.1 | 5.5 | 7,473 / 413 | $0.0025 |

### Claude Sonnet 5, agent

| Question | Files | Symbols | Citations valid | Findings | Model s | Run s | Tokens in / out | Est. cost |
|---|---|---|---|---|---|---|---|---|
| typer-params-to-options | 2/2 | 2/2 | 5/5 | 5 | 16.3 | 28.0 | 22,588 / 1,447 | $0.0596 |
| typer-single-command | 1/1 | 1/1 | 1/1 | 1 | 10.5 | 27.0 | 27,938 / 660 | $0.0625 |
| typer-enum-choices | 1/1 | 2/2 | 10/10 | 5 | 17.1 | 30.3 | 24,269 / 1,578 | $0.0643 |
| typer-context-parameter | 1/1 | 1/2 | 5/5 | 4 | 15.7 | 31.8 | 21,020 / 1,168 | $0.0537 |
| typer-annotated | 1/1 | 1/1 | 8/8 | 8 | 18.0 | 28.2 | 23,552 / 1,881 | $0.0659 |
| typer-pretty-exceptions | 1/1 | 2/2 | 5/5 | 5 | 11.2 | 17.0 | 6,675 / 1,152 | $0.0249 |
| typer-rich-help | 2/2 | 1/1 | 5/5 | 5 | 11.4 | 17.8 | 8,504 / 1,113 | $0.0281 |
| typer-did-you-mean | 1/1 | 1/1 | 8/8 | 5 | 13.1 | 23.5 | 19,347 / 1,406 | $0.0528 |
| typer-install-completion | 1/1 | 2/3 | 3/3 | 3 | 9.3 | 16.1 | 5,482 / 816 | $0.0191 |
| typer-cli-runner | 1/1 | 2/2 | 5/5 | 4 | 17.3 | 31.4 | 26,549 / 1,206 | $0.0652 |
| typer-find-app | 1/1 | 1/1 | 4/4 | 4 | 17.1 | 32.8 | 28,090 / 1,278 | $0.0690 |
| ky-retry-decision | 1/2 | 1/1 | 7/7 | 7 | 13.8 | 18.9 | 9,667 / 1,438 | $0.0337 |
| ky-retry-after | 2/2 | 2/2 | 6/6 | 5 | 26.4 | 43.4 | 67,077 / 1,874 | $0.1529 |
| ky-retry-delay | 1/1 | 1/1 | 6/6 | 5 | 12.6 | 18.9 | 9,618 / 1,131 | $0.0305 |
| ky-timeout | 2/2 | 2/2 | 7/7 | 6 | 19.6 | 28.6 | 20,880 / 1,618 | $0.0579 |
| ky-before-request-hooks | 0/1 | 0/1 | 7/7 | 5 | 11.6 | 16.9 | 9,634 / 1,189 | $0.0312 |
| ky-extend | 2/2 | 1/2 | 4/4 | 4 | 9.6 | 15.2 | 9,600 / 855 | $0.0277 |
| ky-json-body | 0/1 | 0/1 | 7/7 | 6 | 23.4 | 43.2 | 84,599 / 1,561 | $0.1848 |
| ky-prefix-base-url | 1/1 | 1/1 | 3/3 | 3 | 13.5 | 18.8 | 11,032 / 826 | $0.0303 |
| ky-max-response-size | 1/1 | 1/1 | 4/4 | 4 | 14.2 | 24.4 | 25,020 / 1,060 | $0.0606 |

### Claude Sonnet 5, one-shot

| Question | Files | Symbols | Citations valid | Findings | Model s | Run s | Tokens in / out | Est. cost |
|---|---|---|---|---|---|---|---|---|
| typer-params-to-options | 2/2 | 1/2 | 5/5 | 4 | 17.5 | 23.1 | 8,729 / 1,437 | $0.0318 |
| typer-single-command | 0/1 | 0/1 | 0/0 | 0 | 4.4 | 9.6 | 7,017 / 374 | $0.0178 |
| typer-enum-choices | 1/1 | 1/2 | 3/3 | 3 | 10.0 | 17.4 | 4,990 / 771 | $0.0177 |
| typer-context-parameter | 0/1 | 0/2 | 4/4 | 3 | 10.7 | 16.8 | 4,903 / 799 | $0.0178 |
| typer-annotated | 0/1 | 0/1 | 7/7 | 5 | 14.6 | 20.8 | 8,946 / 1,498 | $0.0329 |
| typer-pretty-exceptions | 1/1 | 2/2 | 4/4 | 4 | 11.2 | 18.0 | 6,408 / 1,169 | $0.0245 |
| typer-rich-help | 2/2 | 1/1 | 9/9 | 7 | 16.2 | 26.0 | 8,505 / 1,676 | $0.0338 |
| typer-did-you-mean | 1/1 | 0/1 | 3/3 | 2 | 7.3 | 14.0 | 8,335 / 533 | $0.0220 |
| typer-install-completion | 1/1 | 2/3 | 3/3 | 3 | 8.8 | 14.7 | 5,240 / 874 | $0.0192 |
| typer-cli-runner | 1/1 | 1/2 | 7/7 | 6 | 12.8 | 18.8 | 5,521 / 1,370 | $0.0247 |
| typer-find-app | 0/1 | 0/1 | 0/0 | 0 | 3.5 | 7.7 | 7,141 / 183 | $0.0161 |
| ky-retry-decision | 1/2 | 1/1 | 9/9 | 9 | 15.0 | 20.4 | 9,592 / 1,782 | $0.0370 |
| ky-retry-after | 0/2 | 0/2 | 9/9 | 5 | 9.3 | 15.4 | 9,273 / 1,154 | $0.0301 |
| ky-retry-delay | 1/1 | 1/1 | 7/7 | 5 | 12.0 | 17.2 | 9,379 / 1,215 | $0.0309 |
| ky-timeout | 1/2 | 0/2 | 7/7 | 6 | 14.2 | 19.5 | 6,785 / 1,417 | $0.0277 |
| ky-before-request-hooks | 0/1 | 0/1 | 8/9 | 7 | 16.8 | 21.7 | 9,405 / 1,421 | $0.0330 |
| ky-extend | 2/2 | 1/2 | 6/6 | 5 | 11.2 | 16.2 | 9,421 / 1,126 | $0.0301 |
| ky-json-body | 0/1 | 0/1 | 6/6 | 6 | 11.4 | 16.5 | 11,208 / 1,279 | $0.0352 |
| ky-prefix-base-url | 1/1 | 1/1 | 5/5 | 5 | 11.6 | 17.0 | 10,913 / 1,233 | $0.0342 |
| ky-max-response-size | 0/1 | 0/1 | 5/5 | 4 | 10.2 | 15.3 | 10,548 / 989 | $0.0310 |
