# Per-run cost cap with shadow pricing and graceful degradation

Every run carries a USD budget in graph state (default $0.02). Token usage is read from each model response's `usage_metadata` and priced from a small, reviewed YAML price table. We don't depend on a third-party price dump. Free-tier models are charged at the paid-tier "shadow" price of the equivalent model, so the cap and cost reporting mean something before real money is spent. At 80% of budget, remaining steps switch to the cheapest configured model. At 100%, the run stops and returns a partial report that says it was truncated. The planner's step count gives a pre-flight estimate. The hosted demo also has a per-IP rate limit and a daily run cap; bring-your-own-key lifts both.

## Considered Options

- **Learned difficulty router (RouteLLM):** stale, needs OpenAI embeddings, and was calibrated on chat, not repository questions. Rules based on plan size and step type are enough and easy to debug.
