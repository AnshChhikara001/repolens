# Tests come after all other code in a search

Test files use a question's words more than the code that does the work: ky's `test/hooks.ts` names every hook option, and httpx's `tests/test_decoders.py` has `test_gzip`, `test_brotli`, ... For three Eval questions, tests filled the 24 search candidates, so the reranker never saw the source and the first search showed none of it. Sonnet 5 one-shot then said it couldn't answer, and the agents had to guess better search words.

So a search sorts every test Chunk after every other Chunk, and only then by the fused keyword and vector score. A test is a file in a `test`, `tests`, `__tests__`, `spec` or `specs` folder, or one named `test_*.py`, `*_test.py`, `tests.py`, `conftest.py`, `*.test.*`, `*.spec.*` or `*_test.go`. A query that says test, tests, tested, testing, spec or specs as a word (`test_gzip` counts, `latest` and `TestClient` don't) is searched as before, so tests stay findable by name. `read` and `define` aren't affected.

The first search now shows an expected file for 26 of 29 Eval questions, against 21 before, and file recall rose in every setup ([results](../../evals/results/tests-below-source.md)).

## Considered Options

- **A score penalty for tests:** the vector ranking holds every Chunk, so any fixed penalty is a guess, and the cross-encoder reranks tests back to the top: on `httpx-content-decoding` it scored six tests above every source Chunk.
- **Leave it to the agent:** Sonnet 5 usually searched again with the code's words, but one-shot Runs and Gemini couldn't, and the extra searches cost tokens.

## Consequences

- In practice a search shows tests only if its query mentions tests, or if the Snapshot has fewer non-test Chunks than the search's limit. The agent's prompt says that tests come last unless the query mentions tests.
- A JavaScript test named by a string, such as `test('beforeRequest hook can return a Response')`, is found only by a query that also says "test".
- ky's `test-d/` type tests aren't matched, and are searched like source.
