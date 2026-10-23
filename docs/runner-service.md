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
