# Restart the local runner from a connection error

The app connection-error panel checks the host-configured local runner API
when a transport error occurs. If it is offline, it offers **Restart local backend**.
This is an app UI recovery action, independent of graph elements, node settings,
canvas banners, activity views or browser-supplied Runner URLs.
The click starts only the API process. It does not run the graph, launch a
model turn, change the approved ceiling, clear a ledger, or retry an uncertain
dispatch. Once ready, the user explicitly runs the graph or inspects a prior run.
Exhausted allowances are shown separately from an offline connection.

Opt in on the trusted Langflow host with `LAOMEDO_RUNNER_SERVICE_FILE` pointing
to a private JSON file. The browser cannot choose a command, source, token,
budget or arbitrary endpoint. Example host configuration (replace paths):

```json
{
  "provider": "claude",
  "state": "C:/LocalRuntime/claude/runner",
  "skill_store": "C:/LocalRuntime/claude/registry",
  "source": "C:/LocalRuntime/claude/source",
  "executable": "C:/InstalledClaude/claude.exe",
  "port": 8769,
  "max_model_turns": 1
}
```

The state, registry and source must satisfy their normal runner checks, including
keeping registry data outside Git. Use an existing state directory to preserve
the API token and turn ledger. Claude requires the separately installed Claude
adapter and its supported official CLI/subscription login. The service does not
copy credentials. For Codex, use `provider: "codex"` and omit `executable`; its
normal Docker prerequisites and default runner options still apply.

Authenticated status/start routes select the configured host service when no URL
is supplied. Legacy explicit URLs must still match exactly. They return only service state and remaining turns,
never configuration paths, logs or credentials. An authenticated `/v1/health`
checks the configured API/provider without dispatch. An unknown listener or
authentication mismatch cannot be replaced. Repeated clicks in one app worker
are idempotent. Startup output stays in the private state `service-startup.log`;
startup failures retain a retry action. No service is stopped when a verification
turn ceiling is exhausted: process availability and model authorization are
separate concerns. The operator remains responsible for the service lifetime.

Scope: one configured service per app host, loopback IPv4 URL with exact port,
and the existing host Python environment. This is not a remote process manager.
Internal test providers are control tests, not live acceptance.

## Dependencies and limits

This change is stacked on the shared node-error presenter in PR #184. The app
error panel composes that presenter with recovery, preserving its single set of
safe diagnostics, including run/request IDs. Node popovers do not mount recovery.
Apply the combined overlay once to the pinned upstream checkout; do not apply two
independent error-panel transforms. Specifications depend on specs PR #392.
Claude startup additionally requires the separately installed adapter from PR #180;
Codex startup does not require that adapter. The host must have the provider CLI's
ordinary login available. Custom CLAUDE_CONFIG_DIR profiles are not forwarded.

All authenticated app users can request startup of this one configured API. Enable
this host control only where those users are authorized to manage that local service.
Routed failures returned as node output, rather than app build errors, currently do
not open this recovery panel. No live Codex startup acceptance is claimed.

Startup requires a Python interpreter (including the supported embedded runtime),
with dependencies installed for that interpreter. A frozen non-Python launcher
is outside this control. The child working directory is the trusted app installation,
not the runner state directory; bootstrap and module selection are fixed.
