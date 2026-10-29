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

Graph-wide dispatch reservations, feedback scheduling and downstream requirement
discovery stay outside the Agent module. Failure presentation preserves catalogue
codes and safe identities; an acknowledged request is not a completed execution.
Known embedded source revisions need backed-up migration; unknown consumers are
not declared compatible merely because this entrypoint exists.
