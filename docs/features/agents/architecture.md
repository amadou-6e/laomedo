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
