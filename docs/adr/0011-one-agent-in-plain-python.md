# One agent in plain Python, without LangChain or LangGraph

M1 answered questions through LangChain chat models in a LangGraph `StateGraph`, and the plan was to grow that graph into a supervisor with parallel specialists (ADR-0001), a per-run cost cap (ADR-0004), guardrail classifiers (ADR-0005), a write action (ADR-0006) and a hosted demo (ADR-0009). The one-shot baseline showed that finding the right code was the problem: citations were almost always valid, but only about half the expected files were cited ([baseline](../../evals/results/baseline.md)). More agents wouldn't find more code, so we narrowed the project to one agent, the Code Navigator, that searches and reads until it can answer, and measured it on the eval. With the graph down to a loop, we removed LangChain and LangGraph and wrote the loop and the model layer in plain Python.

- **One agent loop.** Each Agent step is one model call that returns one structured action: a Tool call (`search`, `read`, `define`) or the answer. There is no native tool calling, so every model that returns JSON works the same way. The last step may only answer.
- **Bounded by steps and lines, not by dollars.** A Run takes at most 8 Agent steps, a Tool result shows at most 500 lines and a Run at most 1,500. The Report shows model calls, tokens and time; the Run log records every call, step and Tool result; the eval estimates cost at list prices.
- **A small model layer.** An `LLM` protocol with one method, `structured(system, user, schema)`, and adapters for Gemini (`google-genai`) and the Anthropic API (`anthropic`). `CHAT_MODEL` is `provider:model`, default `google:gemini-3.1-flash-lite` on the free tier. Other providers plug in through the `LOCAL_MODELS` file, which defines `llm(name, timeout)`. Tests use a scripted fake.

The agent took Claude Sonnet 5 from 52% to 85–92% expected-file recall, and Gemini 3.1 Flash-Lite from 58–64% to 66–71% ([results](../../evals/results/agent.md)).

## Considered Options

- **Keep LangGraph for a one-node loop:** the graph added state reducers, a checkpointer we didn't use and pyright workarounds (no `py.typed`) for what is a `for` loop.
- **LangChain tool calling (`bind_tools`):** tool-call support and quirks differ per provider and model; one structured action works the same everywhere and is easy to fake in tests.
- **Keep the cost cap:** it needed a reviewed price table for every model, and the $0.02 budget was about one Gemini Flash Run at paid prices. Capping steps and lines bounds a Run without pricing it.

## Consequences

- Supersedes ADR-0001, ADR-0004, ADR-0006 (no write actions) and ADR-0009 (no hosted demo). ADR-0003 holds except for `init_chat_model`, Groq and prices in `LOCAL_MODELS`. ADR-0005 holds only for the reranker and the untrusted-data wrapping. Git history Tools, guardrails, a hosted demo and a web UI may come in M3.
- Chat model timeouts, retries and the Gemini rate-limit wait (ADR-0003) now live in our adapters instead of LangChain's clients.
