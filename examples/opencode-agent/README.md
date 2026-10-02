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
The broker uses a random per-run bearer capability and admits one command at a
time. It binds to `0.0.0.0` for Docker Desktop bridge routing, so LAN exposure
and network isolation remain outside the tested boundary. The controller mounts
the private auth file read-only over its session auth path. The persistent
session directory has only an empty mount placeholder, not a second plaintext
credential copy. Workers receive no auth mount and use Docker `--network none`.
The OpenCode controller still needs network for its model API and authenticated
command broker. The runner API requires a separate persisted capability file under
private state. For a Langflow component, mount it read-only and set
`LAOMEDO_OPENCODE_RUNNER_TOKEN_FILE` to its container path.

The terminal login was located in the active Console account in `opencode.db`.
`auth list` reports legacy provider credentials and did not describe that login.
`debug config` redacts credentials and must never be used as credential input.
`opencode_auth.console_provider` reads only the active account/access-token and
organization metadata through a read-only connection, requests official account
configuration with JSON headers, rejects redirects/untrusted origins/redactions,
and copies only the selected Go credential and routing context to private state.
No refresh token or personal profile is copied. A private validity record binds
the selected key digest and Console expiry; the runner rejects an expired or
near-expiry Console token before reserving a turn. The official client remains
responsible for refresh. The read-only database connection closes explicitly.

The first two submitted turns failed with provider HTTP 401 because an earlier
handoff copied a redacted value. No native tool results were produced. The
failed turns remain in the cumulative ledger. Subsequent bounded tests below
supersede those initial acceptance gaps without erasing the failure history.

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
ledger was 11/14 at that point. The saved Langflow flow's Runner URL
was then updated to `http://host.docker.internal:8768` and read back with its
six nodes and five edges intact. Successful model-backed flow calls before that
update used a per-run port 8768 override. Network
isolation, exhaustive credential-route auditing, fresh UI Stop and hosted or
multi-user use remain outside the verified prototype.

The saved flow was then run without node tweaks. Attempt 12 reached the runner,
loaded both pinned skills and checked the private paths, but its worker command
failed after the agent appended a period to the fixture filename. Attempt 13
used the exact command and completed with worker exit zero, fixture amber/3,
host-verified marker, both native skill loads and queryable runner status.
The controller view contained only the pinned skills; worker path-presence
checks denied the tested private locations. The selected provider key was absent
from the saved/exported flow, tracked repositories and run results. See
`saved-flow-proof-evidence.json` and `saved_flow_proof.py`.

The review fixes add exact pinned-skill revalidation before dispatch and after
each completed turn, pre-dispatch cancellation checks, cleanup when controller
setup fails, early Console expiry checks, bounded broker concurrency, and
deduplication of tool parts by call ID. A canary-only Docker smoke test and a
no-model provider preflight passed. Saved-flow attempt 14 then completed
with the read-only auth mount and no node tweaks; both skills loaded and all
bounded worker/credential checks passed. See `review-fixes-evidence.json`.
The ledger is now 14/14. No further model turn is authorized. These checks do
not establish exhaustive isolation, an atomic cancel/dispatch boundary, or
fresh UI Stop.

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
