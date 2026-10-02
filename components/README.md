# Laomedo Codex Agent for Langflow

Operator-installed custom component for pinned Langflow 1.12.3. This wraps the
existing local Docker Codex runner; it does not replace Langflow's built-in Agent
or implement its tool interface. The historical `LaomedoRunner` embedded in
`examples/skill-agent-pilot/pilot-flow.json` remains unchanged and compatible.

Mount this directory read-only into the Langflow container and configure
`LANGFLOW_COMPONENTS_PATH=/app/custom_components`. The category package is
`laomedo/`, containing `__init__.py` and `codex_agent.py`. Restart the test server
after code updates; inspect its component catalog for `LaomedoCodexAgent` before
importing a flow. The runtime must have the existing local runner reachable at
`http://host.docker.internal:8765`; native local installations use localhost.

This is a proposed deployment configuration until the operator approves startup.
Keep the existing server and its data volume separate from the acceptance server.
Do not mount Codex credentials, native sessions, the Docker socket or private runner
state into Langflow. The component needs only the loopback runner API.

## Inputs and outputs

Fresh: supply task, immutable whole-skill ID/revision, model and effort.
Resume: set operation to resume and supply the prior structured Run Reference;
its completed status, thread, model/effort and exact post-run hash are required.
Connect Data to Prior Run, or paste its serialized object into advanced Prior Run
JSON for a manual/API invocation. Data handle inputs are not persisted inline by
Langflow's saved-flow builder; the JSON input is the explicit persisted alternative.
Status/cancel: supply a prior run reference containing its run ID; these submit
no model turns. Cancel requests retain the runner's status and evidence.

Answer is a Langflow Message; Run Reference is Data containing answer, run/thread
IDs, state, post-run hash, model/effort, skill revision/use evidence, artifact/trace
references, error category and unknown usage. Both outputs share one dispatch per
component build. A new explicit build submits a new request; automatic retry is
not implemented. Trace references are opaque identifiers, not raw transcripts.

Invalid input fails before HTTP. Runner failures raise errors naming known run ID
and category; transport timeouts cannot establish whether remote execution stopped.
Langflow UI Stop is not claimed to cancel a remote start: synchronous runner start
does not return its run ID until completion. Use explicit cancel with a known run
ID; never interpret client interruption as sandbox denial or runner cancellation.

## Checks

Run `python tests/langflow/test_codex_component.py` inside the pinned Langflow
image with this repository available. It uses a synthetic runner and no credentials
or model turns. Run the existing `python -m unittest discover -s tests` on the host as well.
Real imported-flow acceptance needs a separately authorized model-turn ledger.

Automatic UI Stop propagation is tracked in
[follow-up #22](https://github.com/amadou-6e/laomedo/issues/22); explicit cancel
with a known run ID remains available in this node.

Reference: [Langflow custom components](https://docs.langflow.org/components-custom-components).
Newer documentation features must be checked against the installed 1.12.3 runtime.
