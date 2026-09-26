# Small classifiers for the Repo Intelligence Agent (JEV, laya, and alternatives)

> Update 2026-09-26: embeddings moved from bge-small to OpenAI `text-embedding-3-small` (ADR-0010). The routing and reranking ideas below still apply.

Checked 2026-09-24. Figures come from primary sources (vendor docs, model cards, HF/GitHub/PyPI APIs) unless marked *secondary* or *estimate*.

## TL;DR

- **JEV is real.** TypeSafe AI's hosted "System One" decision model `jev-1.13.0` launched 2026-09-15 [1][2]. API only, no weights, $0.042 per 1M input tokens [3]. The claim that "login is disabled" is **not confirmed**: the console shows a normal sign-in [4], and the docs mention an early-access waitlist [2] and rate limits that "can change without notice" because of demand [3].
- **laya is real, but it isn't from TypeSafe.** It's `convaiinnovations/laya`, an Apache-2.0 open-weights clone of JEV built on ModernBERT-large (421M params), with a JEV-compatible server [5]. It's six days old. By its own README, the base checkpoints score **near chance zero-shot** on typed decisions and ship over-confident [5].
- **Neither is a good guardrail.** TypeSafe's docs say injected instructions in the state "can move the answer" [6]. For indirect injection in repo files, use **Llama Prompt Guard 2 (22M)** [12] and scan chunks once at ingest.
- For secrets, use **gitleaks or detect-secrets**. These are deterministic tools, not ML, and they beat any classifier here. For intent and off-topic routing, reuse **bge-small** with cosine similarity. For chunk relevance, use a 22M **cross-encoder reranker** through fastembed.
- **Skip** model-difficulty routers (RouteLLM), Llama Guard, and JEV/laya. With a $1–1.5 budget, a Gemini free tier, and an LLM planner that runs anyway, they add complexity without saving anything real.

## Verification of JEV / laya

### What was searched

| Where | Query | Result |
|---|---|---|
| typesafe.ai (WebFetch) | home, blog, docs, console | Real company and product. JEV is described as a "System One Model" [1][2] |
| docs.typesafe.ai `llms.txt` + pages | models, API, jaggedness, guardrails cookbook, coding-agents | Full docs exist [3][6][7] |
| console.typesafe.ai | login page | Normal Google/email sign-in. No "disabled" banner at fetch time [4] |
| GitHub API `orgs/typesafe-ai` | repos | Official SDKs (`typesafe-sdk-python`, `-js`, MIT), `skills`, `system-one-adapter-python` [8]. No model weights |
| HF API `models?author=` | `typesafe`, `typesafe-ai`, `typesafeai`, `TypeSafe`, `TypeSafeAI` | Only `TypeSafeAI` exists: an **unverified** org holding 2 "Step-5-Preview" image-text models, created 2026-09-20, not linked from typesafe.ai. Treat it as unofficial |
| HF API `models?search=` | `JEV`, `jev`, `laya` | Many third-party "Jev-Style", "open-jev", GGUF/ONNX/CoreML re-uploads. The original is `convaiinnovations/laya` (created 2026-09-18) [5] |
| PyPI | `laya`, `typesafe-sdk` | `laya` 0.3.20, Apache-2.0, first release 2026-09-18 [9]. `typesafe-sdk` 0.7.1 |
| GitHub | `NandhaKishorM/laya`, "typesafe jev" search | laya repo created 2026-09-18: 22.4k stars, 128 open issues, Apache-2.0 [10]. Large "awesome-jev" ecosystem |
| Independent benchmarks | AbdelStark/jev-benchmarks, nibzard/decision-model-benchmark | Both measure hosted JEV at a p50 of about 236–276 ms [11a][11b] |
| arXiv | — | No paper found for JEV or laya. RLCD is described only in vendor docs and the laya README |

Only secondary pages (not verified) say: $40M led by DCVC, 140k waitlist sign-ups in 36 h, founder "co-invented RLHF". The official blog does name Diogo Almeida as founder [2].

### JEV (TypeSafe AI), verified facts

- **What it is:** a non-autoregressive "System One" model. You send `state` plus typed questions (`choice`, `score`, and `noul` = probability of yes/no). It returns typed answers with per-option probabilities and a confidence value. It never generates text [1][2][7].
- **Architecture and params:** **not disclosed.** Trained with "RLCD" (RL against proper scoring rules) [2].
- **Labels:** custom, zero-shot, defined per request. No fine-tuning per customer [3].
- **Context and limits:** 64k tokens per request (32k for state plus the longest question). 250k tok/s and 1,200 req/min, and these limits "are adjusting dynamically" [3]. English is the primary language [3].
- **Latency:** vendor says 70–500 ms end to end [2]. Measured p50 by third parties is 236–276 ms [11a][11b].
- **Pricing:** $0.042 per 1M input tokens. Output is free [3].
- **Weights:** hosted API only. No local run, so CPU or M1 support doesn't apply.
- **Known weaknesses (vendor's own list) [6]:** literal reading, math and counting, dates, multi-hop indirection, large noisy state, and **"State is data, and jev-1.13 does not treat it as hostile by default… an injected instruction… can move the answer."**
- **Maturity:** about 9 days old, v1.13. The ecosystem is noisy, with many unofficial "open-jev" re-uploads on HF.

### laya (Convai Innovations), verified facts [5][9][10]

- **Checkpoints:**
  - `laya`: ModernBERT-large, 421M params, 512 ctx, English. HF safetensors reports 421,293,830 params (F16).
  - `laya-multilingual`: mmBERT-base, 322M params, 1k ctx (up to 8k).
  - `laya-typed-decisions`: the fine-tuned variant.
- **API:** same typed-question shape as JEV. `laya-serve` exposes `POST /v1/systemone`, compatible with JEV clients. Integrations are available for LangChain/LangGraph and MCP. Install with `pip install laya` (needs torch and transformers). Weights load from safetensors, and the repo's Python helpers make no network calls (checked `rl_agent_api.py`).
- **Size and latency:**
  - Download is about 808 MB (English) and 647 MB (multilingual).
  - Vendor figures are 32.8–39.5 ms on a T4 GPU and **193–464 ms on CPU** with checkpoints preloaded.
  - In fp32 on an 8 GB M1, expect about 1.7 GB of RAM (estimate).
- **Accuracy (self-reported):**
  - Zero-shot moderation/safety: 0.797.
  - Base checkpoint on typed-decisions: 0.362. That is below the 0.461 majority-class baseline. Only the fine-tuned variant reaches 0.766.
  - Banking77: 0.425.
  - Ships over-confident (ECE 0.466, falling to 0.081 only after refitting temperature on your own data).
- **Known bugs (README):** the `noul` answer can follow its label wording instead of the input (issue #156). `act_probability` carries no usable signal (issue #185).
- **Maturity:** 6 days old, hype-driven star count, HF API reports 0 downloads (as of the check) and 3.3k likes. Not a production dependency yet.

## Alternatives table

| Option | What it does | Size (params) | License / gating | CPU / 8 GB M1 | Notes |
|---|---|---|---|---|---|
| **Llama-Prompt-Guard-2-22M** [12] | Binary benign/malicious (injection + jailbreak) | 22M backbone (DeBERTa-xsmall). About 71M total incl. embeddings per HF | Llama 4 Community License. **Gated, manual approval** on HF | Yes. 19.3 ms on A100. CPU: expect tens of ms per 512-token chunk (estimate) | 512-token window, so split longer text. 8 languages. Vulnerable to adaptive attacks |
| Llama-Prompt-Guard-2-86M [13] | Same, multilingual | 86M backbone (mDeBERTa-base). About 279M total | Same gating | Yes, slower (92.4 ms on A100) | Better on non-English |
| protectai/deberta-v3-base-prompt-injection-v2 [14] | Binary injection | 184M | Apache-2.0, **ungated** | Yes. ONNX via Optimum | English only. **Does not detect jailbreaks**. False positives on system prompts. **Archived** (llm-guard also archived [15]) |
| Llama Guard 3-1B / 3-8B / 4-12B [16] | Content-safety hazard taxonomy (LLM-based) | 1.5B / 8B / 12B | Llama licenses, gated | 1B is feasible but slow. 8B/12B are not realistic on 8 GB | Wrong tool: covers harm categories, not injection or repo risks |
| aurelio-labs/semantic-router [17] | Embedding-similarity routing to named routes | Uses your encoder (FastEmbed supported) | MIT | Yes | Maintained (push 2026-09). A thin layer over what bge-small already does |
| lm-sys/RouteLLM [18] | Strong/weak model router (`mf` etc.) | Tiny routers | Apache-2.0 | Yes | Last push 2024-08. `mf`/`sw_ranking` **require OPENAI_API_KEY for embeddings**. Calibrated on Chatbot Arena chat, not repo tasks |
| GLiClass edge-v3.0 / modern-base-v2.0 [19] | Zero-shot multi-label classification | 32.7M / 151M | Apache-2.0 | Yes | Zero-shot labels without examples |
| MoritzLaurer ModernBERT-base / deberta-v3-base zeroshot-v2.0 [20] | NLI-style zero-shot | 150M / 184M | Apache-2.0 / MIT | Yes | One forward pass per label, so cost grows with the label count |
| **BAAI/bge-small-en-v1.5** (already in stack) [21] | Embeddings; cosine to route exemplars | 33M | MIT | Yes, a few ms per query | No new dependency |
| **fastembed TextCrossEncoder** ms-marco-MiniLM-L-6-v2 [22] | Rerank query/chunk pairs | 22.7M | fastembed Apache-2.0 | Yes | Same library we already use |
| Presidio [23] | PII detection/anonymization (regex + NER) | Needs a spaCy model | MIT (repo now `data-privacy-stack/presidio`) | Yes | Useful only if we redact person data |
| gitleaks [24] / detect-secrets [25] | Secret scanning (regex + entropy) | No model | MIT / Apache-2.0 | Yes, milliseconds per file | Deterministic and auditable |
| JEV [3] | Typed decisions, hosted | Undisclosed | Proprietary API, early access | N/A (hosted) | See above |
| laya [5] | Typed decisions, local | 421M / 322M | Apache-2.0, ungated | Yes, but about 1.7 GB RAM and 0.2–0.5 s/call | See above |

## Fit per use case

**(a) Supervisor tool/agent routing.**
- A classifier can't produce a plan. The plan-and-execute supervisor needs an LLM call anyway, so replacing it with JEV/laya saves nothing.
- Where it helps: a **fast path** for obvious single-agent queries such as "any CVEs in deps?" → Dependency/Security only, or "who touched X last?" → History Analyst only. Here bge-small cosine to 5–10 exemplars per route skips the planner call. When below the threshold, fall back to the LLM planner.
- Verdict: small but real savings, near-zero cost to add. JEV and laya are overkill because the same result comes from embeddings we already compute.

**(b) Cheap vs strong model routing by difficulty.**
- The cost cap already downgrades models.
- RouteLLM is stale and needs OpenAI embeddings [18]. JEV/laya "score" questions would need calibration on our own data [5][6].
- With a $1–1.5 total budget and dev on the Gemini free tier, simple rules work as well and are debuggable: step count from the plan, input tokens, and which sub-agent is running (for example, Report Writer gets the strong model and the others get the cheap one).
- Verdict: **overkill.**

**(c) Guardrails.**
- **Direct injection:** the only user is the operator, so risk is low. Still, running the same scanner on the user query costs nothing.
- **Indirect injection (the real risk):** READMEs, docs, issue/PR bodies, and comments flow into Code Navigator's RAG and into the Report Writer. The "open issue" tool is the one write action, and human approval already gates it.
  - Add Prompt Guard 2 22M at **ingest time**, once per chunk, cached by content hash. Store an `injection_score` on each chunk.
  - Drop or quarantine chunks above the threshold, and wrap retrieved text in "untrusted data" delimiters.
  - Show flagged chunks in the approval prompt.
  - It is a 512-token classifier, so chunk sizes already fit.
  - Expect false positives on docs that contain imperative setup instructions. Tune the threshold on a few real repos.
  - Don't use JEV or laya for this: their own docs and README say adversarial state moves answers, and laya's safety score is general moderation (0.797 zero-shot), not injection detection [5][6].
- **Secrets:** run gitleaks or detect-secrets over files before indexing and over the final report. Redact matches.
- **PII:** GitHub author emails are already public, and a regex redaction in the report is enough. Presidio is optional.

**(d) Other LLM-call savings.**
- **Off-topic queries:** add an `on_topic` field to the planner's structured output (no extra call), or use a bge-small similarity threshold against a "repo questions" centroid to reject before any LLM call.
- **Chunk relevance filtering:** after bge-small top-k, rerank with the 22M cross-encoder and keep the top 5. This cuts context tokens into Code Navigator and Report Writer, which is the largest recurring token cost.
- **Issue/commit triage labels** (bug/feature/docs/security) for History Analyst stats: use a GLiClass-edge zero-shot model or bge-small exemplars instead of one LLM call per issue. This matters when a repo has hundreds of issues.

## Recommendation

Adopt the following. RAM total is well under 1 GB.

| Component | Choice | Why | Size / CPU latency |
|---|---|---|---|
| Indirect and direct injection scan (ingest + user query) | **Llama-Prompt-Guard-2-22M** (fallback if gating is slow: protectai v2, archived, English only) | Purpose-built and small. One pass per chunk at ingest. Scores can be stored with the vectors | About 71M total params. About 0.3 GB fp32 (estimate). Tens of ms per chunk on M1 (estimate; measure) |
| Secret detection | **gitleaks** (or detect-secrets if we want Python-only) | Deterministic, fast, standard | No model. Milliseconds per file |
| Fast-path routing + off-topic reject | **bge-small cosine** (hand-rolled, or semantic-router with FastEmbed) | Already loaded. Skips planner calls on trivial queries | 33M. A few ms per query |
| Retrieved-chunk relevance filter | **fastembed TextCrossEncoder, ms-marco-MiniLM-L-6-v2** | Cuts context tokens sent to the LLM. Same library | 22.7M. Roughly 20–60 ms for 20 pairs (estimate) |
| Issue/commit categorization (optional) | **GLiClass edge-v3.0** or bge-small exemplars | Replaces per-item LLM calls in bulk stats | 32.7M. A few ms per item |

Do not adopt:
- **Difficulty router (RouteLLM or JEV/laya scores):** rules in the cost cap are enough.
- **Llama Guard:** wrong taxonomy and too big.
- **Presidio:** regex suffices unless we start handling non-public PII.
- **JEV:** hosted, closed, unstable access and limits, not injection-robust. It is nearly free at $0.042/Mtok, but it is another key plus a waitlist.
- **laya:** 1.7 GB RAM, 0.2–0.5 s on CPU, near-chance zero-shot on typed decisions, known bugs, 6 days old.

If we want to demo the "typed decision" pattern for the portfolio, TypeSafe's `system-one-adapter-python` runs the same `Choice/Score/Noul` interface on Gemini [8]. `laya-serve` can later swap in a local JEV-compatible endpoint [5]. That is an experiment, not a cost saving.

## Sources

- [1] TypeSafe home: https://typesafe.ai
- [2] Introducing System One Models & Jev (official blog): https://typesafe.ai/blog/introducing-system-one-models-and-jev
- [3] Models (pricing, limits, context, data, language): https://docs.typesafe.ai/models.md
- [4] Console sign-in: https://console.typesafe.ai/
- [5] laya model card: https://huggingface.co/convaiinnovations/laya (README, `rl_agent_config.json`, `eval/results.md`)
- [6] Jev 1.13 jaggedness: https://docs.typesafe.ai/model-jaggedness/jev-1.13.md
- [7] Docs index / primitives / coding agents: https://docs.typesafe.ai/llms.txt , https://docs.typesafe.ai/introduction/coding-agents.md
- [8] TypeSafe GitHub org: https://github.com/typesafe-ai (e.g. https://github.com/typesafe-ai/system-one-adapter-python)
- [9] laya on PyPI: https://pypi.org/project/laya/
- [10] laya GitHub: https://github.com/NandhaKishorM/laya
- [11a] https://github.com/AbdelStark/jev-benchmarks
- [11b] https://github.com/nibzard/decision-model-benchmark
- [12] https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-22M
- [13] https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M
- [14] https://huggingface.co/protectai/deberta-v3-base-prompt-injection-v2
- [15] https://github.com/protectai/llm-guard (archived)
- [16] https://huggingface.co/meta-llama/Llama-Guard-3-1B , https://huggingface.co/meta-llama/Llama-Guard-3-8B , https://huggingface.co/meta-llama/Llama-Guard-4-12B
- [17] https://github.com/aurelio-labs/semantic-router
- [18] https://github.com/lm-sys/RouteLLM
- [19] https://huggingface.co/knowledgator/gliclass-edge-v3.0 , https://huggingface.co/knowledgator/gliclass-modern-base-v2.0-init , https://github.com/Knowledgator/GLiClass
- [20] https://huggingface.co/MoritzLaurer/ModernBERT-base-zeroshot-v2.0 , https://huggingface.co/MoritzLaurer/deberta-v3-base-zeroshot-v2.0
- [21] https://huggingface.co/BAAI/bge-small-en-v1.5
- [22] https://github.com/qdrant/fastembed (Rerankers section) , https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2
- [23] https://github.com/data-privacy-stack/presidio (redirects from microsoft/presidio)
- [24] https://github.com/gitleaks/gitleaks
- [25] https://github.com/Yelp/detect-secrets

Param counts, gating, and licenses come from `huggingface.co/api/models/<id>`. Stars and archive status come from `api.github.com/repos/<repo>`, both queried 2026-09-24.
