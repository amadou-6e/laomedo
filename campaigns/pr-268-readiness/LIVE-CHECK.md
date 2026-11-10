# Scoped title-only feedback preparation

Prepared against Laomedo `db2c43f3` on 2026-11-10. `live_feedback.py --checkout
<pr-268-worktree>` performs only reads, imports a synthetic pinned instruction
and creates `flow.json` / `proposal.json`. Preparation returned writes=0 and
model_task_submitted=false. The synthetic Skill contains no private source.

Execution is pending explicit human approval of the exact proposal. It requires
an external approval file containing `human_authorized: true` and the unchanged
`proposal` object. Do not create that approval file without the human's reply.
The proposed scope is one Codex task, temporary title marker on PR268, independent
readback and exact original-title restoration, at most two PATCH attempts. All
other writes are refused by the experiment transport. No issue mutation exists.
No new grant or model task was issued during preparation.

The harness owns a separate loopback PR service on 8785 and private runtime state
outside Git. Normal launchers, runners and the existing read-only service are
unchanged. On an uncertain effect, inspect the independent remote outcome before
any restoration decision; do not replay the agent task. Completion requires
confirmed restoration, actual graph/runner evidence and reviewer coverage.

Earlier native UI checks at source `70df3c59`: actual GitHub discovery, label
clear, fuzzy `recovry` selecting PR264, no-match popup and explicit selection.
No mutation or Agent task was performed by `selectors.cjs`.

## Authorized attempts, 2026-11-10

The human authorized the scoped check, then renewed the dedicated Docker login
and explicitly authorized one retry after the first task failed authentication.
The first submitted task was ffdef593-82cc-4d92-8090-31790b73a397; the retry was
6baed8fe-2ff7-4731-8d0b-3cf52612052e. Both failed runner authentication before a
proposal or GitHub write. The retry reported HTTP401 invalid_jwt while refreshing
its dedicated login. Stored login status alone did not establish validity.

Both attempts made zero PATCH calls and zero effects; the original PR title
remained unchanged. The harness revoked its scoped grants and stopped its own
service. No successful feedback acceptance is claimed. The two single-task
approvals are consumed; do not issue another task under either old approval.
A preliminary missing native graph run-context error submitted no task; the
harness now supplies the owner and run context required by the real executor.
