# Agent workflows

One builder exports current Agent graphs for Codex, Claude or OpenCode. Provider
policy and runtime behavior belong to the installed Agent implementation, not to
an example-specific runner. The builder reads actual component definitions and
uses the maintained Skill graph port helper; it does not dispatch a model, import
a Skill, read credentials or start a service.

## Prerequisites

Use the declared Langflow environment with this checkout's installed Laomedo
package and components. Configure the selected real local runner and its login
using the [Agent documentation](../../docs/features/agents/README.md). Select the
model and effort from that runner's current catalogue. A Skill is optional; if
used, export an existing registry reference containing `skill_id` and `revision_id`.

## Build and inspect

```powershell
python examples/agents/build_flow.py --provider codex --model MODEL --effort EFFORT --runner-url http://127.0.0.1:8765 --task "Read README.md and summarize its purpose. Do not edit files or use subagents." --output agent-flow.json
```

Replace MODEL and EFFORT with actual catalogue values. Use `--provider claude` or
`--provider opencode` with that runner's URL. `--reference path/to/reference.json`
connects the selected immutable Skill to the Agent. `--workflow resume` adds an
explicit second turn on the first run; `--workflow handoff` passes its answer and
provenance to a fresh independent second Agent. Resume requires `--follow-up`.
For handoff, that option overrides the selected answer as the second task.

For an MCP example, build a fresh graph with an optional Skill Reference, import
it, then drag an existing registered MCP server from Langflow's MCP sidebar.
Select its tools and connect **Toolset → Agent.MCP Tools**, alongside the Skill
edge. The builder does not copy server configuration or credentials into a new
node. See [MCP setup and current acceptance limits](../../docs/features/agents/mcp-tools.md).

Import the generated file into Langflow. Inspect its inputs, run it intentionally,
and view answer/run outputs and retained Activity. Resume preserves the native
run identity; handoff creates an independent run. A completed build validates only
serialized graph structure. It is not real execution, recovery, browser or provider
acceptance. No new real-workflow verification is claimed for this consolidated
builder yet. Historical execution evidence stays on `exp`, with its original
revision and limitations.

Generated graphs contain the supplied task/reference and should be kept private
when those inputs are private. Do not commit credentials or local runtime state.

Current boundary: Codex and OpenCode expose the provenance handoff input;
Claude currently does not.
The builder refuses handoff for a component lacking that port instead of silently
omitting provenance. This is an existing provider-interface constraint, not parity
that this consolidation implements.
