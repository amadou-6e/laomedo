# EXP-100 S12: bounded real-provider integration

Frozen prospectively before executable probe implementation or acceptance.
Issue: https://github.com/amadou-6e/laomedo/issues/100. Governing specs:
`04fade6d88cc4c6d5c494c7e566c5cacbad93b09`, agent-execution validation and
design/mediated-cli-transport. Source base `bf443a23d06f741665cc212623a1ce3c35319088`.
Owner explicitly approved this bounded live test on 2026-10-10.

## Fixed authority and budget

Identity: `exp100-live-s12-20261010-a`, single consumed attempt, exclusive
claim in the fixed private temporary campaign directory. Zero model turns,
at most ONE issue POST and 80 real-provider read requests, 600-second overall
deadline, 30-second command deadline and 30-second cleanup acceptance bound.
The only mutating repository is `ga84jog/laomedo-exp104-disposable-20261007`.
`amadou-6e/laomedo` is read-only for Actions run listing and existing job
`114224703478`, run `38056050461` (the accepted #134 final-head CI).
No branch/workflow changes, issue edits/deletions, service installation or
host-credential fallback. Exact configured source/manifest and independent
pre-run approval are required before claiming the identity.

The sole reviewed issue request is frozen here:

```json
{"title":"Laomedo EXP-100 S12 reviewed integration test","body":"exp100-live-s12-20261010-a-reviewed-issue\nDisposable one-shot mediated issue-create acceptance test. No automatic retry.","marker":"exp100-live-s12-20261010-a-reviewed-issue","reviewed_proposal_id":"exp100-live-s12-20261010-a-proposal"}
```

The host constructs this exact snapshot before issuing the grant. A caller
proposal selector alone is not approval. An altered request must fail locally
without a provider write. Only explicit `GH_LAOMEDO` in the user-selected
credential file is used, host-side; the token is never passed to Docker,
argv, environment, traces or artifacts. User repository-only confirmation is
authoritative. Separate connection/grant bindings for each repository; no
cross-repository invocation under a disposable-repository grant.

## Execution and controls

Use the pinned Git-capable image from accepted S11, normal `gh` on the
agent container PATH, production CLI adapter/client, MediationStore,
MediationHTTPService and GitHubRestTransport over real HTTPS. The host owns
the selected credential. Containers mount only wrapper source and a scoped
capability, never host gh/Git/Codex configuration or the credential file.
Fresh synthetic workspace; no model execution or Git push/fetch in this test.

Before the one POST, read-only mediated preflight must succeed: PR list,
issue list, exact fixed GraphQL query, repository REST GET, Actions run list
and the fixed real Actions job read. Capture whether list items exist;
empty lists alone do not prove positive issue parsing. Refuse unsupported
CLI commands, credential export and a wrong repository with exact codes and
zero provider dispatch; an altered reviewed issue request must be denied.

Then send the exact reviewed issue once using a fresh effect ID. If confirmed,
read its exact number back through normal `gh issue view`, list REST and
fixed GraphQL; confirm exact title/body/marker and filter PRs from issue
lists. Public repository GET and job status/IDs must match independent
read-only baseline requests. Baselines use the same explicit host transport
credential source, never ambient gh. They are HTTP semantic controls, not
a claim of native high-level CLI output parity. Baseline calls count toward
the same 80-read cap; GraphQL POST is read-only and counted as a read.

Repeat the exact saved confirmed request host-side once; zero additional
provider calls, same confirmed identity. This is host effect replay, not a
literal CLI retry. Revoked grants must refuse before dispatch. Inspect the
durable issue effect's run/grant/operation/hash/state. Capture actual
container environment KEYS and mount DESTINATIONS only. Cleanup exact
name/labels/IDs and revoke both grants; record verification and elapsed time.

## Failure, recording and interpretation

The POST limit is independently enforced at the provider opener. Record its
attempt before opening the request. No transport retry, no redirect, no
automatic re-dispatch after lost response/crash/timeout, no new effect ID.
Any incomplete preflight, refusal, ambiguous response, changed fixture,
missing positive, exceeded bound or cleanup failure makes the result
incomplete; preserve it and consume the identity. Never infer no effect
from a failed lookup. A confirmed explicit rejection is not success.

Machine observation contains only fixed fixture references, safe codes,
selected IDs/statuses, output hashes, exact known issue bytes, call counts,
durable attribution and cleanup/inventory. No arbitrary provider errors,
headers, token values, host source paths or login material. Preserve original
bytes and pin SHA-256. Tests run synthetic controls, not the live probe.
Independent pre/post-run review and specs evidence precede promotion/closure.

This supports only the selected #100 real-provider lanes. Earlier S10/S11
and closed #104 evidence remain separate. No generic Git/gh parity, paging,
large-data guarantee, hostile-process confinement, #93/#97/#22 or Q11 pass.
