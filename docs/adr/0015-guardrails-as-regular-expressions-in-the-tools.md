# Guardrails as regular expressions in the Tools

Repository content is untrusted: a comment or docstring can be written to take over the model, and code can hold leaked credentials. ADR-0005 planned Llama Prompt Guard 2 at ingest and gitleaks over files and Reports. We check both with plain regular expressions in `guardrails.py`, at the one place repository text reaches a prompt: the Tools.

- **Quarantined chunks.** Before a Tool shows a Chunk, it checks the whole Chunk for phrases that tell a model what to do, like "ignore all previous instructions" or a note addressed to AI assistants. A Chunk that has one is a Quarantined chunk: the Tool names it ("Hidden … it looks like a prompt injection") but never shows its lines. Its lines are not in the Lines read, so no Citation to them survives the verifier. The Report, the Run log and the web page list it.
- **Secrets.** Before a Tool shows a Chunk, it replaces token formats gitleaks knows (AWS, GitHub, OpenAI, Anthropic, Google, Slack, Stripe, private keys, bearer tokens) and secret-looking values assigned to names like `password` or `api_key` with `[REDACTED]`, line by line, so line numbers stay right. The model never sees a secret, and the Report's claims and answer and the web page's cited code are redacted again in case it quotes one anyway.
- **Untrusted data.** The system prompt still says the code is untrusted data, and the main defence stays the Citation contract (ADR-0007): the Report rests only on lines the model was shown.

On the 6 Snapshots ingested locally (8,968 Chunks), no Chunk was quarantined and 18 Chunks had a value redacted, all passwords and tokens in tests.

## Considered Options

- **Llama Prompt Guard 2 (22M) at ingest:** better recall on rephrased attacks, but it is gated on Hugging Face, needs a second model at runtime and a score stored per Chunk, so every Snapshot would be ingested again, and it would run on CPU next to the reranker.
- **gitleaks:** a Go binary to install in the image and run on files, for patterns we can keep in one Python list.
- **Checking at ingest:** a stored flag per Chunk means a new pattern needs every Snapshot ingested again. Checking in the Tools costs a few regexes over at most 1,500 lines per Run and needs no schema change.
- **Hiding only the matching lines:** an injection runs over several lines and a phrase match finds one of them, so the whole Chunk is hidden.
- **Scanning the question:** the question comes from the person running the Run, not from the repository.

## Consequences

- The patterns catch common phrasings, not a determined attacker who rewords the injection. They are measured by the planted fixture in `tests/fixtures/untrusted_repo`, not by an injection eval.
- Each Chunk is checked on its own. A phrase split between two 150-line windows of one long definition isn't caught; a private key split that way is still redacted in both.
- Code that discusses injections, like `guardrails.py` itself, would be quarantined if it quoted the phrases, so its comments describe them instead.
- A Quarantined chunk is invisible to the model, so a question about that code can't be answered from it.
- A redacted test password can no longer be quoted in an answer.
