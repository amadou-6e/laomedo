# GitHub Issue node

Tracking: Laomedo #160, specs #374. Requires the pinned Langflow 1.12.3 runtime
and the small frontend overlay for stale discovery/dependent-selection handling.
Copy components/laomedo/github_issue.py into the installed custom category or
compile it through Langflow's custom-component API.

The node has Repository URL, searchable multi-select Labels (ALL must match),
Issue picker, optional incoming Issue Reference and Operation. State defaults
to open, with closed/all under advanced parameters. It fetches current content
on each build; all outputs in one build share one execution. Changing an issue
title refreshes its display label without replacing its number.

Outputs: Issue Data, readable Task Message and Operation Result. Result states
are not_requested/succeeded/failed/unknown. Failed or uncertain results stop the
Task branch, so unavailable issue data is not sent as an agent prompt. Wire the
result to a condition when handling failures. A second Issue node can receive
the first node's Issue output as its reference, avoiding a workflow cycle.

## Host connection

Run `python -m laomedo.github.issues.github_issue_server --repository owner/repo
--github-token-file <existing-host-connection-file> --github-token-key GH_LAOMEDO
--connection-id <registered-id> --connection-generation <generation>
--api-token-file <existing-control-token-file> --mediation-store <private-ledger>
--grant-bindings <private-binding-file>`. Supply one explicit existing provider
connection; the service does not read ambient gh/Codex authentication. The
alternative --github-token-env names an explicitly configured environment key.
Neither is a browser-login implementation or production vault.

The Langflow backend uses LAOMEDO_GITHUB_ISSUE_URL and
LAOMEDO_GITHUB_ISSUE_TOKEN_FILE (defaults to the existing backend control-token
mount). GitHub credentials, the binding file and mediation ledger stay on the
host and outside agent mounts. Each service instance permits its configured
repository only. No external redirect or arbitrary API tunnel is provided.

The protected binding file maps a nonsecret opaque grant_ref to the existing
broker token, run_id and repository. It must be outside version control and is
never a graph field or export. Only the host runtime populates it. It does not
mint grants; an absent binding leaves writes unavailable. Mediation grants must
explicitly permit issue_update and enumerate target_issues; they retain their
existing expiry, revocation and connection-generation checks. When changing a
provider credential across service restart, increment its registered generation
and retire old bindings; restart alone is not credential-lifecycle automation.

Example runtime Operation Data (no credential):

```json
{"action":"modify","request_id":"run-stage-effect","grant_ref":"opaque-reference",
 "changes":{"title":"Updated title","body":"Updated body","labels":["backend"]}}
```

Close omits changes. Modify patches only supplied fields; labels replace the
whole set, and [] clears them. Target overrides and other fields are refused.
The host persists the exact request identity and expected issue digest before
invoking the existing mediation ledger. A timeout/lost response stays unknown;
reusing its identity never dispatches a second PATCH. A different identity also
cannot bypass an unresolved write to the same issue. Reconciliation requires
the existing explicit retry-approval path, not an automatic retry.

The grant is rechecked immediately before PATCH, after the preceding reads, so
expiry/revocation during those reads prevents dispatch. Revocation cannot retract
a request already sent to GitHub. The read-before-write comparison is optimistic,
not GitHub atomic CAS. The
confirmed result is checked against acknowledgement and a fresh readback.
The operation intent contains private issue text and must remain in the private
ledger. Transport/API logs do not contain raw provider errors or credentials.

## Verification

Host tests: `python -m unittest discover -s tests -p test_live_github_issue.py`.
Pinned native tests: `python -m unittest discover -s tests/langflow -p test_github_issue.py`.
Browser tests: `tests/browser/github_issue.cjs <manifest>` and
`tests/browser/github_issue_operation.cjs <manifest>` with Playwright/Edge.
The latter supports operation_action close or modify. The held-response regression
is `tests/browser/github_issue_stale.cjs <manifest>`; it requires the fixture after
close, so two open issues remain before its label/issue selection setup.

Start the fake backend with `python tests/browser/serve_github_issue_fixture.py
--manifest <ignored-manifest>`. Its model/provider calls are fake, and the frozen
fixture clock deliberately keeps its dummy capability usable for browser checks;
real expiry/revocation are tested separately. Import source-only and incoming-
operation graphs with `python tests/browser/prepare_github_issue_fixture.py
--manifest <ignored-manifest> --action read|modify|close` against a disposable
loopback viewer (default port 7866). Run read before modify before close, or reset
the fixture between cases. The helper refuses manifests without fake-no-network.
Manifest fields are provider
fake-no-network, url, operation_url, operation_action and flow IDs. The actual
Run component button submits /api/v2/workflows in this pinned frontend; it is
not equivalent to merely calling the component's Python methods.

No live writes, provider login or model turns are part of these tests. Existing
frozen EXP-139 examples remain historical evidence and are not relabelled live.
See [activation draft](DEPLOYMENT.md); current running services are unchanged.


## Issue inspection controls

Issue viewer replaces Code on GitHub Issue. It fetches fresh scoped data without
running an operation. Open in GitHub opens the exact selected issue in a separate
tab. Empty/invalid picker selection disables opening; reference-only runtime
inputs are not guessed. Markdown skips HTML and remote images. The overlay also
recognizes namespaced custom-component IDs. Browser regression:
`tests/browser/issue_viewer.cjs <fake-manifest>`; native endpoint checks:
`tests/langflow/test_issue_inspection.py`. See [activation draft](ISSUE-VIEWER-DEPLOYMENT.md).
