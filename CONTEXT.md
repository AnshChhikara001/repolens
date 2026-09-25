# repolens

A multi-agent system that answers questions about a GitHub repository and backs every claim with a verifiable citation.

## Language

### Runs and planning

**Run**:
One question answered end to end against one Snapshot, from plan to Report.
_Avoid_: job, session, query

**Plan**:
The Supervisor's typed list of Steps for a Run. A Run has at most 3 Plans (the first plus 2 re-plans).
_Avoid_: task list, strategy

**Step**:
One unit of work in a Plan, assigned to a single Specialist, with a goal and the Steps it depends on.
_Avoid_: task, action

**Supervisor**:
The graph node that writes Plans, reviews Findings, and decides whether to re-plan or report.
_Avoid_: orchestrator, router, manager

**Specialist**:
A sub-agent with its own tools and a narrow job: Code Navigator, History Analyst, Dependency Analyst, or Report Writer.
_Avoid_: worker, sub-agent, tool

**Fast path**:
A Run routed straight to one Specialist by embedding similarity, skipping the planning LLM call.

### Evidence

**Snapshot**:
A repository at a pinned commit SHA, written `owner/repo@sha`. All analysis and caching is keyed by Snapshot.
_Avoid_: checkout, clone, version

**Chunk**:
A function-, class- or section-level slice of a file in a Snapshot, with its path, line range and symbol.
_Avoid_: document, passage

**Quarantined chunk**:
A Chunk whose injection score is over threshold. It is kept out of prompts and shown for review.

**Finding**:
A single structured claim returned by a Specialist, carrying at least one Citation.
_Avoid_: result, observation, answer

**Citation**:
A pointer that can be checked against a Snapshot: a `path:line-range`, or a commit, PR or issue number.
_Avoid_: reference, source

**Report**:
The final answer to a Run, composed only from Findings with valid Citations.
_Avoid_: response, summary

### Cost and safety

**Budget**:
The USD cap for one Run, tracked in graph state.
_Avoid_: limit, quota

**Shadow cost**:
What a free-tier call would have cost at the paid price of the equivalent model.

**Downgrade**:
Switching the remaining Steps to the cheapest configured model once 80% of the Budget is spent.

**Write action**:
Any tool call that changes state on GitHub. The only one is opening an issue in the Sandbox repo, and it needs human approval.

**Sandbox repo**:
`repolens-sandbox`, the only repository Write actions may target. It also holds the planted-injection fixtures.

**Showcase run**:
A precomputed Run on a well-known repository, served statically on the demo.
