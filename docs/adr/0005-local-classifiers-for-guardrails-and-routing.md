# Small local classifiers for guardrails and cheap routing

Repository content (READMEs, docs, issues, code comments) is untrusted input and a real channel for indirect prompt injection. At ingest, each chunk is scored once by Llama Prompt Guard 2 (22M), cached by content hash. Chunks above threshold are quarantined, and flagged content is shown on the approval screen. Files and the final report are scanned with gitleaks for secrets. Retrieved text is always wrapped as untrusted data in prompts. Obvious single-specialist questions and off-topic questions are routed by cosine similarity on the bge-small embeddings we already compute, which skips the planner LLM call. A 22M cross-encoder reranks retrieved chunks to cut context tokens. All of these run on CPU in well under 1 GB of RAM.

## Considered Options

- **JEV (TypeSafe AI) / laya:** JEV is hosted-only and in early access, and its own documentation says injected text in the input can change answers. laya is near chance zero-shot per its own README. Neither is suitable as a guardrail. Details are in `docs/research/small-classifiers.md`.
- **Llama Guard:** a content-safety taxonomy, not injection detection, and too large for the target hardware.
- **ProtectAI DeBERTa v2:** fallback if gated access to Prompt Guard 2 isn't granted. English-only and archived.
