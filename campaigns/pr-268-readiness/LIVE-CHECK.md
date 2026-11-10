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
