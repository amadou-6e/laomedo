# Agent architecture

The [Agent components](../../../components/laomedo) expose graph controls and
translate node requests into runner operations. Execution belongs to
`src/laomedo/agents/`, including runtime, provider adapters, contracts, feedback,
handoffs and workspaces.

`src/laomedo/host/` owns managed runner startup, host credentials, leases and
mediation. `src/laomedo/activity/` owns retained execution activity and provider
projections. `src/laomedo/integrations/langflow/` connects these concerns to the app.
See [package layout](../../architecture/package-layout.md) for canonical imports.

Private credentials and persisted execution state stay outside the Python
package. [Host mediation](mediation/host-services.md) authorizes external effects;
an agent-proposed operation is distinct from a confirmed result.
[Activity](activity.md) inspects retained work without dispatching another model
request. [Runner recovery](runner/local-service.md) manages service availability
separately from graph execution.

The lifecycle is provider-neutral: `agents/agents/base/agent.py` owns shared state and
request orchestration, while each `agents/agents/{codex,claude,opencode}` adapter
owns native execution and runtime binding. Claude and OpenCode do not inherit
Codex. The common graph component belongs to `agents/interface/langflow/` (through the stable `integrations/langflow/agent/component.py` entrypoint);
provider nodes retain their existing public identities. See the
[provider boundary](../../architecture/package-layout.md#provider-neutral-agent-boundary)
for capabilities, record compatibility and migration requirements.
