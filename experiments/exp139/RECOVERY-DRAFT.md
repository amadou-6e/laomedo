# Proposed recovery configuration, not activated

The approved original profile was tested unchanged. Turn 1 completed native
evidence closure and both output precheck calls (reject, then accept), created
the exact report, and honestly reported task failure because Git could not write
its config or index lock. The imported graph routed this to failure. No push or
PR attempt was reserved. A deliberate failure-case launch was then refused
before a model submission because the mediated supervisor requires a GitHub
scope even for a run intended to have no GitHub grant. The durable ledger is 1/4.

Proposed changes requiring configuration approval:

1. Add only the explicit `/draft/.git = write` rule shown in
   `GIT-PERMISSIONS-DRAFT.toml` for this disposable campaign. Keep the root read
   rule, workspace write rule, exact auth-file denial and network setting.
   Never change the global provider configuration or other runners.
2. Serve a separate, ordinary non-mediated lease supervisor inside the existing
   independent host service process, on its own private state and loopback port.
   Select it only for the failure/rejection cases, without a GitHub grant or
   mediated capability. The success case keeps the mediated supervisor and its
   original finite handoff. No additional host process is required.
3. Prospectively rebuild/freeze/review a fresh success request identity after
   confirming the failed attempt has no provider writes and its grant is revoked.
   Preserve the original records and the durable ledger. Use at most the three
   remaining submitted turns: fresh success, deliberate failure, downstream pin
   rejection. The original one-push/one-draft-PR attempted-write caps remain.
   No repeat of an unknown provider operation is authorized.

Claude's post-run review requires a host-side Git audit and a credential-free
hostile-config regression before activation: writable `.git` must not allow
fsmonitor, hooks, filters or credential helpers to execute on the host. Supervisor
selection must come only from the host case table, never a graph request field,
and a success case must retain its mediated supervisor. Preserve consumed request
identities across restart. Configuration approval alone does not satisfy these
implementation and independent-review gates.

Credential-free Docker probe against the pinned Codex Git image:

| Profile | Git index lock writable | Git config writable | Dummy auth canary read |
| --- | --- | --- | --- |
| Original | No | No | Denied |
| Exact Git-metadata rule | Yes | Yes | Denied |

The probe used no real credentials, no network and no model turns. It tests the
proposed permission rule, not live recovery. The first live failure must remain
in the results. No draft PR exists yet. This proposal does not establish hosted
isolation or authorization against a process under the same Windows user.
