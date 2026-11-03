# Agent assembly provenance

Issue #205 and draft PR #250 assemble the existing Agent work from
`refactor/237` at `8f7b184573cc0d6655d3b61a59f550d84e67253e` onto
`develop` at `20df788fe776fc0bc0d7576a5f0774880aa9e89d`. The source includes
ownership, lifecycle, typed records and workspace checkpoints `eb1f5e8c`,
`75ce39d3`, `b36f20ed`, `4ff59d59`, `fa33f94d` and `b614cf34`.
The [Agent architecture](../../src/laomedo/agents/README.md) describes the
implemented package boundaries and object vocabulary.

## Scope and preservation

The cut includes Agent providers, their shared lifecycle and public interface,
provider Activity and authentication, workspaces, artifacts, orchestration, host
runner HTTP, daemon-bound leases, graph run records and packaged resources.
GitHub and Skill domain implementations remain independently owned. Skill polish
and GitHub PR #249 are separate changes; the integrated source branch is preserved.
The original assembly matched 162 selected source-branch Python ASTs. That was a
historical relocation check, not an equivalence claim for subsequent bug fixes.

The maintained Agent example is [one graph builder](../../examples/agents/README.md)
using actual component metadata and caller-supplied provider/model/effort/task.
It builds fresh/resume graphs for all three providers. Provenance handoff is
structurally supported only by components exposing that port (Codex/OpenCode).
Building a graph does not establish successful provider execution.

Historical provider examples, campaign callers and their companions are preserved
on [exp](https://github.com/amadou-6e/laomedo/tree/305d5b269dd2cc1086a88b28812ab4e4edd5d6a0/archives/agents-205).
Manifests identify original revisions, paths, byte lengths, SHA256 and Git blob IDs.
A direct source-object audit found newline conversion in earlier archive copies;
all 563 records in that archive were repaired and independently compared with
original source Git blobs at `f5735e84`. Ten additional caller/companion records
were preserved with exact blob checks at `305d5b26`. Historical revisions remain
available; these records do not represent current live acceptance.

The reviewed obsolete root campaign wrappers/suites and the fixed two-Issue Agent
demo have been retired after archival and regression ownership review. Applicable
authority/lease/revocation, publication admission, file replacement, divergent
history, hook isolation and safe failure-receipt checks run against production
APIs in concern-owned tests. Fixed campaign identities, consumed allowances and
prototype receipt contracts remain historical. No production test fetches `exp`.
The GitHub-owned EXP-100 broker CI job and its remaining dependencies are deferred.

## Runtime corrections

Unexpected async worker exceptions finish the host attempt while preserving an
unknown remote outcome. Lost dispatch/poll responses retain request/run identities
without resubmission. Orchestration preserves uncertainty rather than reporting a
definite Agent failure. OpenCode cancellation during setup is checked before the
prompt, and its command worker explicitly has no network.

Codex requires consistent native completion and ACP `end_turn` evidence. Conflicts
produce an unknown outcome. Answers are selected only from the active root thread;
child and unbound messages cannot replace the root answer. Rollout export uses the
immutable image ID and disables networking.

Claude distinguishes pre-dispatch failure from post-dispatch uncertainty, clears
stale answer/snapshot fields on failure and excludes receipts replayed during a
resumed session load from the current attempt. Native notification ordering still
requires real adapter evidence. Normal runners have no experimental turn cap.

## Verification and limitations

The runtime requires the declared py-docker revision `49652f4` and ACP SDK `0.12.1`.
Installed-wheel checks assert the package import origin outside the source tree.
At `2ab48092`, the wheel SHA256 is
`f39d19ccc60c7e6442032f1cfc147ab8c959c9f1edb84f3cc8bd8874fc0e2625`.
Standard installed-wheel core discovery passed 1,159 cases in 396.053 seconds
with 23 explicit skips, outside the checkout with import origin asserted. A prior custom diagnostic lacked the Windows multiprocessing
entry-point guard and is excluded from acceptance. The affected host-service case
passes through standard unittest invocation.

Affected internal checks passed: Codex controller 9; root-answer/runtime 64;
trace/export 13; Claude uncertainty/replay 23; leases 19; organized boundary,
credential and graph-summary controls 35; publication ports 56 with three explicit
platform skips. These are internal controls, not real provider or browser stories.

Claude has approved focused worker/poll, ACP, OpenCode cancellation, migration and
provider corrections at their recorded revisions. The latest async terminal-marker
and publication-port recheck did not complete: the retained reviewer reached its
five-hour limit, reporting reset at 13:00 Europe/Berlin. Full substantive PR review
is incomplete. The split Codex executor's native sandbox/network isolation remains
unverified; direct Docker probe results do not establish that guarantee.

ACP spec PR #403 and implementation PR #214 remain open draft dependencies.
Canonical protocol drift and integration must be resolved before merge. Docker is healthy and the three existing provider images are present. A real
read-only provider audit is awaiting explicit approval for exporting its three
tracked README inputs: automatic approval review rejected that file transfer.
No model request or credential copy was performed in this continuation.
Hosted CI, actual provider/user-story evidence, requesting-owner inspection and
explicit final validation remain acceptance requirements. PR #250 stays draft
and unmerged.

The original assembly increased src Python/MJS physical lines from 32,288 to
36,747 (+4,459), including pre-existing ACP and typed-record work absent from its
base. This historical comparison is not a current reduction or parity claim.
