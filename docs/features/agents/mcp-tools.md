# Connect MCP tools to an Agent

Use the Laomedo app factory with the inspected **LFX 1.12.3** deployment. The app
and runner must use the same local user and private filesystem. Standalone graph
execution without the app lifetime owner refuses MCP registration.

Register the server in Langflow's existing MCP settings, drag that server onto
the graph and select its tools. Enable its native Toolset output and connect it
to the Agent's optional **MCP Tools** input. Connect additional MCP servers to the
same input. A Skill node can still connect independently to **Skill References**.

```text
Skill node ─── Skill References ──> Agent.Skill References
MCP server ─── Toolset ──────────> Agent.MCP Tools
```

This extends the [maintained Agent example](../../../examples/agents/README.md).
Keep registration, credentials and tool selection on the existing MCP node; do
not paste server URLs, credentials or STDIO commands into Agent task inputs.
Only selected tools are exposed, with stable external names; display aliases do
not change the upstream function invoked. Tool approval interactions that cannot
be preserved are explicitly refused.

The app retains connections after **Start** returns. Keep the app open for the
whole run. Resume requires the same selected tools and schemas, with a new live
registration. Missing or changed connections fail explicitly. No external tools
are admitted by an Agent status/cancel operation. Native Langflow graph dependency
materialization still requires editor acceptance; do not treat the component's
operation guard as proof that the upstream node was never built.

## Local host configuration

The default private rendezvous directory is `~/.laomedo/mcp`. The existing
private-state mechanism verifies current-user-only permissions. An existing
directory with unverified permissions is refused rather than silently repaired.

Set `LAOMEDO_MCP_DIRECTORY` to the same absolute private directory for the app and
runner if overriding the default. Managed runner startup forwards only the named
MCP host settings, alongside its existing filtered environment.

Forwarding binds to `127.0.0.1` by default. Controllers use
`host.docker.internal`. Verify this path on the actual Docker Desktop installation.
If needed, set `LAOMEDO_MCP_BIND` to an explicit private host interface and
`LAOMEDO_MCP_CONTROLLER_HOST` to the controller-reachable host alias/private IP.
Wildcard binds are refused; this feature does not change firewall rules. The
existing internal OpenCode broker is unchanged.

`LAOMEDO_MCP_LEASE_SECONDS` controls abandoned-registration expiry (default 120);
runner supervision renews it independently of native ACP event loops. It is not
a model-turn budget or total run duration cap. Registration and call counts are
bounded with `LAOMEDO_MCP_MAX_REGISTRATIONS` and `LAOMEDO_MCP_MAX_CALLS`.

The Codex controller requires the updated owned ACP adapter with scoped HTTP MCP
admission and exact `enabled_tools`. Stock/older adapters reject this capability.
Claude and OpenCode use their existing native MCP interfaces and exact tool
allowlists. Upstream HTTP and STDIO remain owned by Langflow; controllers receive
only a short-lived forwarding capability, never upstream login material.

## Outcomes and verification limits

Calls are dispatched once. A timeout, cancellation or broken connection can leave
effects unknown; never automatically replay such a call. Completion/cancellation,
app shutdown and expired leases revoke access. The bridge does not close other
Langflow clients or their pooled STDIO sessions.

New bridge activity does not retain arguments/results. Provider-native history
can contain model-visible tool content. Scoped forwarding tokens are excluded
from public models and redacted from provider observations.

Current checks cover the actual native tool factory, real local HTTP and STDIO
servers, app-lifetime retention, scoped forwarding and selected-tool rejection.
Status and Cancel omit their MCP input dependencies during native scheduling, so
an unavailable MCP server does not prevent contacting the runner. Shared inputs
needed by another active Agent and explicitly playing an MCP node remain enabled.
The saved graph keeps its connections; fresh work and graph rebuilds restore them.
They do not establish the full editor UI or six real provider/transport cases.
Those remain acceptance work in [issue #280](https://github.com/amadou-6e/laomedo/issues/280).
The governing contract/design is [specification PR #419](https://github.com/amadou-6e/specs/pull/419),
which must merge before the implementation can merge.
