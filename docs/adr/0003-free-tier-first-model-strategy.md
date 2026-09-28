# Free-tier-first model strategy; paid models only for evaluation

The total paid LLM budget for the project is about $1.50. Development, CI and the hosted demo run on free tiers: Gemini Flash / Flash-Lite, with Groq as a fallback. Tests use fake chat models and recorded responses. The OpenAI budget pays for embeddings (ADR-0010, a few cents per repository) and the comparison column in the final eval (about $0.35 per 40-question run on a nano-tier model). A hard spend limit is set in the provider dashboard. Every model is configured through `init_chat_model`, so a provider change is one config line.

## Consequences

- Free tiers have daily request quotas. Full eval runs use Flash-Lite for workers, or are split across days.
- Free-tier prompts may be used by the provider for training. That's acceptable because we only analyse public repositories.
- Local LLMs were rejected: the development machine has 8 GB RAM, which isn't enough for reliable tool calling.
- Every chat-model request has a timeout (`CHAT_TIMEOUT`, default 120s). Built-in providers get a small retry limit, so a slow free tier fails with a clear error instead of stalling a Run.
