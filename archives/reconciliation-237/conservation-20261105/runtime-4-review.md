# BATCH_RUNTIME_4: COMPLETE

All 27 header entries in `runtime-4.txt` are covered, and every one comes from **PR 216**. I found no gaps and no defects; there are two low, optional suggestions. Reading the ranges and finding matching source and tests is coverage, not semantic proof: I ran nothing. This is not an all-23, feature, merge or closure verdict, and the all-23 verdict stays **HOLD**.

**Ranges I actually read from `runtime-4.txt`:** 1–200, 201–400, 401–600, 601–800, 801–1000 and 1001–1171.

**Root `AGENTS.md`:** I relied on the review/merge section I read earlier (lines 34–49) and did not reread it.

**Entries covered** (class-level entries and their method-level versions were each checked):
- `CodexAgent._execute_acp`
- `CodexController` and `.__init__`
- `OpenCodeAgent`, `.model_catalog` and `._execute`
- `CommandBroker`, `.__init__`, `.execute` and `.close`
- `IsolatedOpenCode`, `.__init__`, `.models`, `.history_reader`, `.run`, `._run_acp` and `.close`
- `HttpAgentBridge` and `.dispatch`
- `AgentComponent`, `._run_reference` and `.submission_output`
- `AgentHandoffController` and `.run`
- `envelope`
- `GitCommandRunner` and `.run`

**Origin and owners:**
- Every change in this batch was introduced by old PR 216.
- `src/laomedo/agents/**` belongs to **Agent250**. The same markers (`_retain_attempt_failure`, `runner_runtime_unknown`, `runner_result_pending`, `dispatch_uncertain`, `AgentHandoff(`) are present in `.tools/agent-refactor-205`.
- `src/laomedo/git/command.py` belongs to **Shared255**. `ISOLATED_HTTPS_READ_ONLY` and `_execute_budgeted` are present in `.tools/shared-reconciliation-237`.
- The detailed evidence below is from c8, `.tools/reconciliation-integration-237`.

## Results by contract group

| # | Contract group (entries) | Status | Current evidence (c8) |
|---|---|---|---|
| G1 | Records the first failure and any cleanup failure, never changes the public outcome, and still releases the lock and cancel flag. Covers the Codex agent, Codex controller startup/close, OpenCode agent/catalogue and broker. | **PRESERVED** | **Source:** `codex/agent.py:1067-1122, 1297-1336`; `opencode/agent.py:119-144, 458, 579-652`; `base/agent.py:175-214`; `codex/controller/service.py:130-149, 428-464`.<br>**Tests:** `test_runtime/test_failure_finalization.py`. Codex `:162-355`: first SDK error survives a later lease failure, a `None` finish result doesn't invent cleanup, a record-write failure still releases the lock. Controller `:363`. OpenCode `:386-464`: primary error survives cleanup failure, no snapshot on success, lock released. Also `test_failure_observations.py`. |
| G2 | `ActivityAttemptRecord` replacing dict literals (Codex and OpenCode) | **PRESERVED** | `activity/models.py:80-109`: field order matches the Codex literal; `exclude_unset` drops `fresh_thread` to give the OpenCode shape.<br>Tests: `test_activity/test_records.py:17-24`, `test_codex/test_activity_parity.py`. |
| G3 | `_turn_available` removed from Codex and OpenCode | **INTENTIONALLY_SUPERSEDED (verified)** | **Removal:** no product match under `src`; it survives only in the test helper `tests/test_agents/verification.py:21-45`.<br>**Per-run checks remain:**<br>• Codex: `codex/agent.py:652` (`run_not_dispatchable`), `:798-824` (`cancelled_before_turn`), `:874-1005` (`still_authorized`).<br>• OpenCode: `opencode/agent.py:361-362`.<br>**Tests:** product runs create no `turn-ledger.json` (`test_lifecycle.py:836, 1370, 1688`; `test_opencode/test_runner.py:237, 280, 329, 505`); the counter is diagnostic only (`test_accounting.py:27-38`). |
| G4 | Codex `_answer(events, thread_id)` scoping answers to the root thread | **PRESERVED** | `codex/utils.py:205-216`; `test_codex/test_answer.py:9-42` (child and unbound messages can't replace the root answer). |
| G5 | Codex controller: only `stop_reason == end_turn` counts as completed; anything else is `unknown/runner_runtime_unknown` | **PRESERVED** | `service.py:323-328`; `test_codex/test_acp_controller.py:98-119`. |
| G6 | `CommandBroker`: worker `network_mode='none'`, receipt registered before the job runs, `drained` flag | **PRESERVED** | `opencode/boundary.py:60-61, 135, 155, 230`; `test_opencode/test_boundary.py:374-404` (network none, empty environment, `cap_drop ALL`, read-only `/canonical`). |
| G7 | `IsolatedOpenCode`: typed runtime identity, receipt registration, catalogue cleanup mapping, cancel before dispatch, idempotent close that drains before exact recovery | **PRESERVED** | **Source:**<br>• `boundary.py:240, 257-323, 454-485, 522, 567, 598-651`<br>• `opencode/models.py:13-43`: field order matches the old literal, `provider='opencode'`, and `profile_id` is a JSON value so legacy values still load.<br>• `opencode/agent.py:366-376`: dict comparison when resuming.<br>**Tests:**<br>• `test_opencode/test_records.py:30-42`<br>• `test_failure_finalization.py:45-158`: these call the actual `close`/`models` methods. They cover stop → drain → recover order, leaving unrelated receipts alone, and refusing to confirm cleanup when a resource is pending or not drained.<br>• `test_protocol/test_provider_bindings.py:104-108`<br>**Note:** these tests now exercise the real `close` recovery path (SDK mocked, no Docker), which bears on the earlier runtime-3 "untested `close` recovery" item. Runtime-3's status is unchanged. |
| G8 | Bridge: transport, HTTP or JSON-parse failures become `runner_result_pending` with no resend and the acknowledged run kept; `AgentDispatchResult` shape | **PRESERVED** (and matches the stated pending-bridge supersession) | `interface/bridge.py:166-175, 219-228, 237`; `test_orchestration/test_bridge.py:161-188` (a single send, nothing left active), `:190-238` (POST then GET; the acknowledged run is retained). |
| G9 | Langflow `AgentRunReference` and `AgentSubmission` (schema `laomedo.agent-submission.v1`) | **PRESERVED** | `interface/models.py:7-159, 346-382`; `langflow/component.py:1185-1262` (submission is a dict or None; unconfirmed success can't be promoted).<br>Run references have a literal key-order fixture: `test_interface/test_records.py:10-31`. |
| G10 | Handoff controller: `unknown/interrupted/prepared/running` stop as `dispatch_uncertain`, never `agent_failed` or a retry | **PRESERVED** | `orchestration/controller.py:151, 169`; `test_orchestration/test_controller.py:75-90` (exactly one dispatch), `:118-123`. |
| G11 | `envelope` producing an `AgentHandoff` | **PRESERVED** | Admission happens before the model is built (`orchestration/utils.py:31-85`).<br>Tests: literal handoff, payload, canonical preimage and digest in `test_request_records.py:22-39` and `data/request-records.json`. |
| G12 | `GitCommandRunner`: isolated HTTPS/file read-only profiles, narrow environment allowlist, fixed `-c` policy, budgeted reads with a Windows job and suspended start, one shared cleanup deadline | **PRESERVED** | `git/command.py:44-347` matches the PR 216 delta.<br>Tests:<br>• `test_shared/test_git/test_read_budgets.py:59-110`: exact environment and argv order, including the file-profile prefix.<br>• `:112-142`: rejects overrides and dangerous clone/fetch options; Popen is not called.<br>• `:160-357`: cleanup categories stay distinct; budget and deadline behaviour.<br>• `test_windows.py:101-224`<br>• `test_command.py:114-176` |

## Findings (non-blocking)

**C4-S1 / suggestion / low**
- **Location:** `interface/models.py:304-343, 346-382`. **Owner:** Agent250. **Origin:** PR 216.
- **Issue:** `AgentDispatchResult` and `AgentSubmission` keep the old key order only because the fields are declared in that order. I found no literal key-order test for them, unlike `AgentRunReference`, which has one at `test_records.py:22`.
- **Consequence:** reordering the fields in future would change the serialized dispatch/submission bytes without any test failing.
- **Suggestion:** add `list(result)` order assertions against literal original outputs.
- No current defect.

**C4-S2 / suggestion / low (observation)**
- **Location:** `orchestration/models.py:136-139`; `utils.py:96, 101`. **Owner:** Agent250. **Origin:** PR 216.
- **Issue:** the old envelope copied the caller's `target` and artifact dicts as given (`deepcopy` / `dict(item)`). The typed models now emit keys in a fixed declaration order.
- **Effect:** content and dict equality are unchanged, and the request digest is computed with `sort_keys` (`test_request_records.py:32-39`), so request identity is unaffected. Only the persisted byte order can differ, and only when a caller supplied keys in a non-canonical order.
- **Uncertainty:** I found no consumer that depends on that order within the scope I inspected.

## Gaps and sources not inspected
- **Owner heads:** I didn't compare owner heads to c8 byte for byte. I only grepped for markers in `agent-refactor-205` and `shared-reconciliation-237`.
- **Not consulted:** `github-restored-245`, `skills-followup-206`, raw `pr-216.diff` and `originals/`. I treated the normalized batch as PR 216's delta.
- **Earlier findings 217 and 233:** not part of this batch, so I didn't recheck them here.
- **Execution:** nothing was executed. Several tests are skipped when `py_docker` isn't installed.
- **No real-environment execution:** no real Docker, provider, Windows job-object or browser runs were performed, and no new model execution.
- **Remaining gates:** full provider/browser/manual publication and the owner merge gates remain separate.