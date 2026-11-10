# Graph-connected MCP tools

This capability owns frozen external tool grants and invocation-scoped forwarding
between native Langflow MCP clients and isolated Agent controllers. It does not
register upstream servers or own Langflow's pooled clients. Issue: #280.

| Module | Responsibility and objects |
| --- | --- |
| `models.py` | `McpTool`, `McpManifest`, `McpRegistration`: validated non-secret identities and private admission projections |
| `settings.py` | `McpSettings`: host-owned local rendezvous, private bind address and bounded resources |
| `registry.py` | `McpRegistry`: application-lifetime registration, exact grants, one-call dispatch and revocation |
| `server.py` | `McpServer`, `McpRequestHandler`: authenticated MCP forwarding, no upstream connection configuration |
| `client.py` | `McpAccess`: runner admission, health, native endpoint projection and release |
| `errors.py` | `McpError`: stable external-tool failure code without upstream diagnostic text |

The native compatibility adapter belongs in
`integrations/langflow/mcp.py`: `LangflowMcpTool` validates the pinned native
closure shape and makes exactly one underlying MCP call. It must preserve input
validation, original tool identity and MCP `isError`, without invoking LFX's retrying
callable, patching shared clients or closing borrowed sessions.

The app lifespan composes with Langflow's existing lifespan and retains the loop
and registry after asynchronous `start` returns. Registration on another loop or
without that owner is refused. Shutdown revokes grants before upstream teardown.
The native-loop and single-call gates must pass before provider integration.

The compatibility checks now exercise real native discovery and actual MCP HTTP
and STDIO calls through the authenticated forwarder after the build coroutine
returns. A registration is claimed by one runner invocation; another run cannot
borrow it. Heartbeats run on a separate thread so native cancellation loops never
perform blocking supervision I/O. Directory custody uses the existing strict
`host/private_state` owner, not a new permission implementation. Full editor and
provider acceptance remain separate and unverified.

Graph and durable task identity contain only the frozen manifest. An opaque local
registration reference is transient admission, verified against that manifest and
excluded from semantic request hashes. Native bearer capabilities remain in
host-private state/configuration and are never upstream server credentials.
Resume requires the same frozen manifest with fresh live registration. Status and
cancel do not materialize upstream nodes. No MCP preserves existing behavior.

Use the existing trusted single-user deployment only. Default to loopback; refuse
wildcard bind addresses. An explicit Docker-reachable private interface may be
configured through common host configuration. No firewall changes or all-interface
fallback. Existing OpenCode internal broker policy remains unchanged.

Selection is an exact frozen allowlist with stable external namespaces; internal
`laomedo` is reserved. Tools requiring unavailable approval interactions are
refused. Do not record arguments/results in new Laomedo activity events. Native
provider traces can still contain model-visible results. Calls are never retried:
timeouts/cancellation leave effects unknown. Bound schemas, payloads, concurrency
and leases. App loss stops external access and fails the attempt closed.

Acceptance requires real native graph execution after `start` returns and all six
Codex/Claude/OpenCode × HTTP/STDIO discovery/invocation cases. Fixture checks do
not establish that acceptance. Full implementation and rendered UI require review.
