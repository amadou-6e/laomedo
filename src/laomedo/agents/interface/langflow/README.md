# Langflow Agent adapter

`component.py` owns `AgentComponent`, the shared implementation used by the three
public provider nodes. The established
`laomedo.integrations.langflow.agent.component` entrypoint delegates here so saved
component identity remains stable. Provider IDs, node names, ports and saved
settings remain unchanged. This package is optional; core imports must not load it.

The public framework methods retain their required names. `_prepare` validates
and builds a request; `_http` crosses the configured runner boundary; output
methods expose the retained outcome. `update_build_config` refreshes model/effort
choices through discovery. Private methods are not alternative application APIs.

In the admitted local-profile app, `provider_connection` selects only an opaque
saved connection ID owned by the framework-injected execution user. There is no
default account or fallback to operator runner settings. The host manager resolves
all runner URLs and token files; graph fields cannot supply native launch paths.
Fresh runs admit the current connection epoch; retained runs resolve their original
epoch for evidence/cancellation and refuse resume after reconnect or disconnect.
Model discovery, Activity and Stop use that same resolved runner. Export and file
import clear the local selector and its display options, requiring explicit rebind.

Graph-wide dispatch reservations, feedback scheduling and downstream requirement
discovery stay outside the Agent module. Failure presentation preserves catalogue
codes and safe identities; an acknowledged request is not a completed execution.
Known embedded source revisions need backed-up migration; unknown consumers are
not declared compatible merely because this entrypoint exists.

The prior-run compatibility input stays present in server templates so Langflow
can preserve existing resume/status/cancel connections across loading and template
refresh. The canvas shows that port only when it has an incoming connection.
Disconnected nodes have no Prior Run setting or run selector; the adapter refuses
operations without an actual supplied reference. It does not infer one from
Activity or silently choose a previous execution.

`errors.py` defines `RunnerResultError`: an invocation failure retaining the safe
run reference for recovery. The established graph-side error import re-exports
that same class. The adapter explicitly calls the graph-owned
`integrations/langflow/output/utils.downstream_requirements` hook when inspecting
its outgoing graph connections; generic output validation remains in the public
Agent output contract. The public contract models do not import graph machinery.

`RunnerRequestError` retains a stable code and a projected `RunnerDiagnostics`
envelope before a new run exists. Submission outputs place it in the existing
run-reference envelope; exception outputs serialize only this bounded envelope
after the code. HTTP 5xx without a new run remains `runner_runtime_unknown`,
with the reported code retained as a separate diagnostic observation.

The saved-connection Claude adapter recovers only an explicit HTTP400 cold
catalogue refusal without a run identity: it discovers using the already pinned
endpoint, then retries that fresh/start dispatch once. Warm or operator-mode
runs and Status/Cancel skip discovery; unknown transport failures are not retried.
