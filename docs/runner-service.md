# Restart the local runner from a connection error

The app connection-error panel checks the host-configured local runner API
when a transport error occurs. If it is offline, it offers **Restart local backend**.
This is an app UI recovery action, independent of graph elements, node settings,
canvas banners, activity views or browser-supplied Runner URLs.
The click starts only the API process. It does not run the graph, launch a
model turn, rewrite historical evidence, or retry an uncertain
dispatch. Once ready, the user explicitly runs the graph or inspects a prior run.
Historical experiment ceilings do not authorize or block normal user runs.

Opt in on the trusted Langflow host with `LAOMEDO_RUNNER_SERVICE_FILE` pointing
to a private JSON file. The browser cannot choose a command, source, token,
or arbitrary endpoint. Example host configuration (replace paths):

```json
{
  "provider": "claude",
  "state": "C:/LocalRuntime/claude/runner",
  "skill_store": "C:/LocalRuntime/claude/registry",
  "source": "C:/LocalRuntime/claude/source",
  "executable": "C:/InstalledClaude/claude.exe",
  "port": 8769
}
```

The state, registry and source must satisfy their normal runner checks, including
keeping registry data outside Git. Use an existing state directory to preserve
the API token and recorded results. Claude requires the separately installed Claude
adapter and its supported official CLI/subscription login. The service does not
copy credentials. For Codex, use `provider: "codex"` and omit `executable`; its
normal Docker prerequisites and default runner options still apply.

Authenticated status/start routes select the configured host service when no URL
is supplied. Legacy explicit URLs must still match exactly. They return only service state and safe reason codes,
never configuration paths, logs or credentials. An authenticated `/v1/health`
checks the configured API/provider without dispatch. An unknown listener or
authentication mismatch cannot be replaced. Repeated clicks in one app worker
are idempotent. Startup output stays in the private state `service-startup.log`;
startup failures retain a retry action. Normal startup has no experiment-wide turn ceiling. Legacy max_model_turns
keys are ignored, and historical turn-ledger.json is preserved as evidence;
ordinary attempt accounting uses a separate attempt-count.json. Bounds for
internal controls belong to experiments/turn_harness.py, which normal services
never import. The operator remains responsible for the service lifetime.

Scope: one configured service per app host, loopback IPv4 URL with exact port,
and the existing host Python environment. This is not a remote process manager.
Internal test providers are control tests, not live acceptance.

## Dependencies and limits

This change is stacked on the shared node-error presenter in PR #184. The bottom-right recovery popup uses the shared error catalogue, preserving one set of
safe diagnostics, including run/request IDs. Node popovers do not mount recovery.
Apply the combined overlay once to the pinned upstream checkout; do not apply two
independent error-panel transforms. Specifications depend on specs PR #392 and the selected A popup standard in
specs PR #393.
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

The approved A card uses compact text, collapsed Technical details and separate
Restart/Dismiss actions. It is portalled outside canvas transforms and stays
within the visible viewport when resized, zoomed or shortened by a keyboard.
Escape inside the card dismisses it and restores prior focus. It never
auto-dismisses, retries the graph, or cancels work when dismissed. Follow-up
cards: #186 (error/stack), #187 (notice/success), #188 (other flow status).
