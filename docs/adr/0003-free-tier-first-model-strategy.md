# Free-tier-first model strategy; paid models only for evaluation

The total paid LLM budget for the project is about $1.50. Development, CI and the hosted demo run on free tiers: Gemini Flash / Flash-Lite, with Groq as a fallback. Tests use fake chat models and recorded responses. The OpenAI budget pays for embeddings (ADR-0010, a few cents per repository) and the comparison column in the final eval (about $0.35 per 40-question run on a nano-tier model). A hard spend limit is set in the provider dashboard. Every built-in model is configured through `init_chat_model`, so a provider change is one config line. Providers kept out of the repository plug in through a `LOCAL_MODELS` file instead (see below).

## Consequences

- Free tiers have daily request quotas. Full eval runs use Flash-Lite for workers, or are split across days.
- Free-tier prompts may be used by the provider for training. That's acceptable because we only analyse public repositories.
- Local LLMs were rejected: the development machine has 8 GB RAM, which isn't enough for reliable tool calling.
- `LOCAL_MODELS` names a Python file that defines `PRICES` and `chat_model(name, timeout)`. It adds hosted providers the repository doesn't ship, not local LLMs. Its prices can only add models, never change reviewed ones, so the ledger and Budget still apply.
- Every chat-model request has a timeout (`CHAT_TIMEOUT`, default 120s). Built-in providers get a small retry limit, so a slow free tier fails with a clear error instead of stalling a Run.
- A Gemini rate limit (429) is the exception: the free tier's per-minute quota says how long to wait, so we wait that long (up to 60s) and retry once. A 429 without a delay, or with a longer one (the daily quota), fails at once.
