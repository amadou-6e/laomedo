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


## Fresh selector and viewer observations, 2026-11-11

A separate native QA app on7861 and grant-free PR read service on8786 use final
PR268 source db2c43f3 and the pinned frontend. The maintained builder produced a
new PR-only flow: no stale-component banners, no Agent and no graph execution.
The complete fresh-selectors.cjs run passed actual state choices, ten discovered
labels, selecting and explicitly clearing bug, fuzzy recovry matching264, no-match
and an unconfigured-repository refusal directly beneath Repository URL. It then
opened the real PR264 viewer and verified its exact external GitHub URL.

The separate viewer-final.cjs check delays forwarding the unchanged readonly
inspection request by2500ms, captures the real pending UI, then verifies the real
GitHub snapshot. This is controlled latency, not a fixture response or a normal
latency measurement. The uncontrolled fast case did not capture loading. Earlier
harness retries fixed duplicate QA IDs, unsupported .git URL spelling, transient
combobox selection and selecting the node before invoking its toolbar. Those
failed harness paths are not successful product acceptance. The final complete
harness and the separate loading check both pass. No PR mutation grant or model
task was issued; isolated mediation counts remain zero.

Claude approved the full PR266 own diff at ce89c388 -> dc6383df and the PR268
consumer guard at dc6383df -> db2c43f3. It approved the inspected current state,
refusal, labels/search/no-match/viewer captures. V-Q1 stale code is resolved. New
V-L1 loading and V-L2 label-cleared captures await their focused visual recheck: the
same session hit quota before that request, reset14:10Berlin2026-11-11. No verdict
exists for that pending request. Actual title-only feedback remains blocked by
runner401 and its two consumed approvals; no third Agent task is authorized.

## Renewed acceptance attempt, 2026-11-11

The owner authorized as many scoped checks as necessary, retaining title-only temporary modification and exact restoration, and approved the shared specification dependency update. Implementation 5a7c1c607d4f53e266c93d8bdc1694689575c75a integrates merged develop/#266; its own patch is byte-for-byte unchanged. Eight final CI checks pass, 72 focused PR tests and three subtests pass. Specs #417 clean parent integration 1de8c867 has unchanged own patch, validator zero errors/one existing warning, and both final CI checks pass.

Preparation now imports a unique synthetic Skill identity for each fresh proposal instead of conflicting with a prior registry import. Preparation submits no task and performs no GitHub writes. A local approval-file BOM was corrected before any task execution. The ensuing authorized single-task graph failed with 401 invalid_jwt/pr_agent_failed: zero PATCH attempts, independently unchanged original title. No immediate replay. Dedicated volume login status reports ChatGPT but does not establish inference authentication. Opened device login in the owner's VS Code terminal; interactive completion is pending. No credentials, login codes, raw login state or private runtime captures are retained here.
