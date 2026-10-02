# Experimental OpenCode adapter

Issue: https://github.com/amadou-6e/laomedo/issues/27.

`laomedo.opencode_runner.OpenCodeRunner` reuses the immutable skill store and
workspace lifecycle. `components/laomedo/opencode_agent.py` provides native
Langflow ports by reusing the existing Codex client. Install the category together
with `components/` on the component server's Python module search path. Nothing
in this change installs it into the running user flow or modifies server settings.

Runtime check: OpenCode 1.18.33, Langflow 1.12.3. Unsupported variants fail, rather
than silently becoming the default. Provider/model is required explicitly. Skills
have OpenCode's kebab-case names; shared registry names with underscores are rejected.

The default runner still requires explicit isolated transport configuration.
`opencode_boundary.IsolatedOpenCode` separates a credential-bearing controller
from disposable command workers. Only native skill loading and the authenticated
MCP command broker are enabled. Workers mount the task workspace and read-only
canonical/store paths; no controller profile, credentials, environment or Docker
socket is mounted. Controller runtime and worker image identities are checked.
The broker is host-accessible with a random per-run bearer capability. Network
isolation and complete native cancellation remain unverified.

The terminal login was located in the active Console account in `opencode.db`.
`auth list` reports legacy provider credentials and did not describe that login.
`debug config` redacts credentials and must never be used as credential input.
`opencode_auth.console_provider` reads only the active account/access-token and
organization metadata through a read-only connection, requests official account
configuration with JSON headers, rejects redirects/untrusted origins/redactions,
and copies only the selected Go credential and routing context to private state.
No refresh token or personal profile is copied; expired tokens require the
official client to refresh. The read-only database connection closes explicitly.

Two earlier submitted turns failed with provider HTTP 401 because the previous
handoff copied a redacted value. No native tool results were produced. Their
ledger remains 2/2 and is not reset. Corrected credential resolution succeeded
without a new model call, but fresh/resume live acceptance awaits further approval.
The boundary's direct command probes passed; agent-originated credential denial,
native skill use, native cancellation and authenticated model completion remain
unverified. This slice does not yet fulfill #27.

Four further turns on 2026-10-02 advanced the ledger to 6/6. Three returned HTTP
401; the final request reached HTTP 400 with an unsupported-protocol error. No tool
result or completed snapshot was observed. The corrected provider configuration
now preserves official Console inference routes and model-specific SDKs instead of
legacy catalog overrides. Runtime preflight confirms Luna uses the Console endpoint
and `@ai-sdk/openai`, but inference with that final correction remains untested.
See `live-evidence.json`. Runner port 8768 avoids the handoff runner on 8767.

Four subsequently authorized turns advanced the ledger to 10/10. Direct terminal
CLI returned the exact diagnostic marker with tools denied. Real imported Langflow
fresh/resume completed, loaded both skills natively and preserved the session
through a runner restart. Host marker readback and worker credential-path denial
were verified. A separate native abort test observed worker disappearance and no
delayed write; its live failed-status race was fixed afterward with a deterministic
regression. See `live-success-evidence.json`. A later authorized live retest
returned `cancelled`, acknowledged native abort, removed the owned worker and
left no delayed write. See `live-cancellation-retest.json`; the cumulative
ledger is 11/14, with three turns unused. The saved Langflow flow still points
to port 8767; successful flow calls used a per-run port 8768 override. Network
isolation, exhaustive credential-route auditing, fresh UI Stop and hosted or
multi-user use remain outside the verified prototype.

Credential-free tests:

```powershell
python -m unittest discover -s tests
```

The Langflow tests run inside the pinned 1.12.3 image with repository files copied
to a temporary directory, without changing installed components:

```text
python tests/langflow/test_opencode_component.py
python tests/langflow/test_codex_component.py
```
