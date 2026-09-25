# Hand-built plan-and-execute supervisor on LangGraph StateGraph

The supervisor emits a typed plan (steps with an agent, a goal and dependencies). Independent steps fan out in parallel via `Send`. The supervisor reviews the findings and either hands off to the Report Writer or re-plans, at most 2 times and 6 steps. We build the graph directly on `StateGraph` rather than using the prebuilt `langgraph-supervisor` or a ReAct-style "pick the next agent" loop. There are two reasons. A plan upfront gives us a cost estimate before any tokens are spent (see ADR-0004). Owning the graph keeps routing, state reducers and the re-plan loop explicit and testable.

## Considered Options

- **ReAct supervisor:** simpler, but it's sequential, and cost is unknown until the run ends.
- **`langgraph-supervisor` prebuilt:** less code, but it hides the routing and state handling this project is meant to show.
- **Swarm / handoffs:** no single place to enforce the budget and guardrails.
