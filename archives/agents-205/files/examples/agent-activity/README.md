# Real agent activity graph

Build with the pinned Langflow Python environment:

```sh
python examples/agent-activity/build_flow.py --skill-store /private/skills
```

This imports the real read-only skill and exports `flow.json`, with embedded
original Codex Agent source. It does not invoke a model. Import that graph into
Langflow after applying the frontend overlay.

Run two independently supervised original Docker runners on ports 8765 and 8767,
using the same real `examples/github-pr` source workspace and skill registry.
The first needs two top-level turns, the second one. Configure the app's private
activity DB and dedicated runner API token as described in
[agent activity](../../docs/features/agents/activity.md). Enable local OTLP on both runners
and the bounded native multi-agent opt-in on the second. Subagent model calls
are additional usage beyond the top-level turn ledger.

Run the graph once, then open **Agents**. The two root invocations can overlap;
the follow-up resumes the first native thread. Inspect messages, the real README
read command and output, per-invocation token deltas, child activity and telemetry.
API-equivalent estimates have explicit pricing assumptions; no subscription bill
is inferred. Missing metadata stays unknown.

This graph uses real agents and integrations. It performs no GitHub writes.
Its successful generation alone is not execution acceptance.
