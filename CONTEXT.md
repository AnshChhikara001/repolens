# repolens

An agentic code Q&A tool that answers questions about a GitHub repository and backs every claim with a citation checked against the pinned commit.

## Language

### Runs

**Run**:
One question answered end to end against one Snapshot, from the first model call to the Report.
_Avoid_: job, session, query

**Code Navigator**:
The agent that looks through a Snapshot for the code that answers the question and returns Findings.
_Avoid_: retriever, searcher

**Agent step**:
One turn of the Code Navigator: a model call that returns a single action, either a Tool call or the answer.
_Avoid_: iteration, hop

**Tool**:
A function the Code Navigator calls in an Agent step to look at the Snapshot, such as searching the code or reading lines of a file.
_Avoid_: action, plugin

**Report Writer**:
The last step of a Run. It writes the answer from the verified Findings only.

**Run log**:
The JSON Lines file a Run writes: its start, every model call with its tokens and latency, every Agent step and Tool result, and its end (with the rejected Citations) or error.
_Avoid_: trace, ledger

### Evidence

**Snapshot**:
A repository at a pinned commit SHA, written `owner/repo@sha`. All analysis and caching is keyed by Snapshot.
_Avoid_: checkout, clone, version

**Chunk**:
A function-, class- or section-level slice of a file in a Snapshot, with its path, line range and symbol. Short module-level code is part of the definition next to it.
_Avoid_: document, passage

**Index version**:
What a Snapshot's stored Chunks depend on: the chunker version and the embedding model. A Snapshot stored under another index version is ingested again.

**Excerpt**:
Lines of one Chunk that a Tool shows the model.
_Avoid_: snippet, hit

**Lines read**:
The lines of each file the model was shown during a Run, however they were fetched. Citations may point only at these lines.

**Finding**:
A single structured claim returned by the Code Navigator, carrying at least one Citation.
_Avoid_: result, observation, answer

**Citation**:
A `path:line-range` in a Snapshot, optionally naming the symbol it points into. It is valid only if every cited line is in the Lines read.
_Avoid_: reference, source

**Report**:
The final answer to a Run, composed only from Findings with valid Citations.
_Avoid_: response, summary

### Evaluation

**Eval question**:
A question pinned to a Snapshot, with the files (and optionally the symbols) a good answer cites.
_Avoid_: test case, benchmark item

**File recall**:
The share of an Eval question's expected files that the Report cites. Symbol recall is the same for expected symbols.

**Citation validity**:
The share of the Citations a model returns that the verifier keeps.
