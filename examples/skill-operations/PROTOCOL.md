# Real Skill operation verification

Prospective protocol, 2026-10-16. New work for implementation #176; this does
not reuse or reset the exhausted PR #170 campaign or its ledger.

Use the existing LaomedoCodexAgent and Docker LocalRunner with a new private
registry, state and independent lease service. Reuse the authorized dedicated
local Codex credential volume; mount no host GitHub token. Maximum **one native
model turn**, with output continuations disabled. Preserve the ledger and all
failures. Do not retry an uncertain invocation or substitute an internal fixture.

Import the existing real `pr-feedback-title` skill from the PR example into the
private registry and import the pinned `skill-operation-editor`. The target
operation must append a reference instruction to SKILL.md and add
references/operation-format.md with the documented PR proposal contract. Both
changes belong to one candidate commit; never publish to Git or promote latest.

Before dispatch verify policy rejects unauthorized skills and stale base refs.
After the graph verify one original Agent run and native turn, exact two changed
paths, parent-linked commit and independently read stored file bytes. Compare
canonical latest and original source files with their pre-run hashes. Recompute
the diff from registry bundles. Replay the same private ticket without another
model turn and prove history count stays fixed. Confirm container cleanup.

Stop runner and lease services after verification. Keep only a loopback read-only
history viewer for user review; its service has no edit policies. Export the exact
two-node graph without tickets or credentials. Record source revision and graph
hashes, result/provenance and limitations. Raw receipts stay in host-private state.

Internal tests cover refused batches, unsafe paths, concurrent edits, replay
conflicts, expiry, reverts and scheduler controls; these are not live acceptance.
Native cancellation and production ownership/promotion are outside this one-turn
campaign. User graph review is required before implementation merge.
