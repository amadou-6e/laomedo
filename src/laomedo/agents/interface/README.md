# Public Agent boundary

This package connects the wider application to Agent capabilities without loading
provider implementations. Canonical data contracts stay independent of the base.
Optional framework adapters load only when requested.

| Concern | Owner | Nomenclature |
| --- | --- | --- |
| HTTP transport | `bridge.py` | `HttpAgentBridge` (initially `RunnerAdapter`): transport-qualified bridge |
| Prepared request | `models.py` | `AgentRequest` (initially `RunnerRequest`): strict request envelope |
| Output requirements | [output](output/README.md) | One validation implementation shared by Agents and callers |
| Langflow adapter | [langflow](langflow/README.md) | `AgentComponent`: framework-specific application adapter |
| Errors | `errors.py` | Re-export canonical Agent errors; no second hierarchy |

The bridge's methods form this vocabulary:

| Method | Inputs/result and effects |
| --- | --- |
| `fresh_request(handoff, request_id)` | Build the native async request and digest; no network dispatch. |
| `dispatch(handoff, *, deadline, cancelled, ...)` | Dispatch a permitted lifecycle request under a deadline; a timeout can leave remote work active. |
| `lookup_request(provider, request_id)` | Authenticated reconciliation; never a second POST. |
| `status(reference)` | Read an existing run; do not create a new identity. |
| `cancel(...)` | Send a cancellation request and retain confirmation separately. |
| `select_artifacts(reference, selection)` | Request an admitted selection from retained output. |

`from_component_request` constructs the request envelope; `with_activity_attempt`
returns a bound copy; `component_arguments` preserves the saved component's
existing `_http(endpoint, payload, method)` calling convention. Persisted keys
remain `runner_*` where already established; Python renaming is not schema migration.

Host HTTP server composition lives in `host/runner/http`, outside these contracts.
Explicit trusted host startup registers providers. Graph input cannot select
Python imports, executable commands or credential locations.
