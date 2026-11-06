## Focused recheck of T1-D1, D2, D3, D5 and D6, plus T2-I1

Four of the five tests-1 blockers are settled. T1-D2 is only partly settled: one narrow gap remains in the Codex controller (T1-D2R below). T1-D4 was my mistake and is withdrawn. The T2-I1 change is a real fix, but the reason given for it doesn't match what I found in Agent250.

**What I read:**
- The whole `resume-20261105/agent-controls-recheck.diff` (224 lines, 7 test files).
- `agent-controls-result.json` and `installed-stale-guard.log`.
- Root `AGENTS.md`. I found no owner `AGENTS.md`/`CLAUDE.md` in `.tools/agent-refactor-205`.
- The source each new test exercises in `.tools/agent-refactor-205`. All the new test methods are present in that worktree.

I used Read/Grep only and ran nothing. The 86-test and 7-test results are your reported runs, not mine. I couldn't recompute the file hashes.

| ID | Result | Evidence |
|---|---|---|
| **T1-D1** | **SETTLED** | See the T1-D1 notes below the table. |
| **T1-D2** | **PARTLY SETTLED** (gap T1-D2R) | See the T1-D2 notes below the table. |
| **T1-D3** | **SETTLED** | `test_output.py:31-35` pins the exact keys `{type,name,description,inputSchema}`, `type == "function"` and the tool name. These match the strict adapter schema at `docker/codex-acp/LaomedoExtension.ts:12-17`. |
| **T1-D5** | **SETTLED** | See the T1-D5 notes below the table. |
| **T1-D6** | **SETTLED** | See the T1-D6 notes below the table. |
| **T1-D4** | **WITHDRAWN (my error)** | I searched for the old method name and message instead of the renamed test. See the T1-D4 notes below the table. |

**T1-D1 notes:**
- The fake backend now calls `on_session` before signalling that it has started.
- That call saves `thread_id` to the run record (`opencode/agent.py:403-407`), so `cancel()` gets past the early return at `:687-693` and calls `backend.cancel()` at `:694`.
- The test checks that the cancel event was set and joins the worker within 5 seconds, before the `finally` fallback. That proves cancellation itself unblocked the run.
- It also checks that both `cancel_acknowledged` and `termination_verified` are False, which matches `:695-701`.
- The direct broker test at `test_boundary.py:31-37` matches `boundary.py:586-589`.

**T1-D2 notes:**
- I traced the new test at `test_session.py:164-196` through `base/acp/session.py:124-204`.
  - **User cancel:** deadline 1, cancel sent, deadline 15, then the clock reads 20, giving `cancel_native_unconfirmed`.
  - **Timeout:** clock 10 ≥ 1 sets `timed_out`, cancel sent, deadline 25, then 30, giving `turn_timeout`.
- Only the session module's `time` is patched, so asyncio's own timing is real.
- The cancel succeeds but the result is still a failure, which shows an acknowledgement is not treated as termination.
- The `pending.cancel()`/`gather` cleanup at `:201-204` is what sets `stopped`, so the pending prompt really is collected. The session also doesn't close the container.

**T1-D5 notes:**
- `test_acp_controller.py:226-245` pins all five fixed probe commands from `controller/service.py:350-360`, each called exactly once. An unknown probe is refused before `exec_probe` runs.
- `:247-256` pins the unsplit path: only `extension("laomedo/preflight", {"check": …})` is called, and unknown probes are refused before the extension runs.
- The `executor` attribute defaults to None at `service.py:45`, so the unsplit path is the one actually exercised.

**T1-D6 notes:**
- `test_codex/test_settings.py` covers both environment variables with six invalid values each (12 cases).
- It checks `.code`, the exact `args`, and that the input value does not appear in `repr`. This matches the root `AGENTS.md` rule to preserve exception codes and arguments.
- The `ValidationError` side and the valid value are still covered by the existing numeric-budget test in `test_shared/test_architecture/test_settings.py`.

**T1-D4 notes:**
- The replacement is `test_installed_package_matches_current_source_files`, at `.tools/shared-reconciliation-237/tests/test_shared/test_architecture/test_packages.py:20-51`. The same method is at the same line in Agent250 and in the combined c8 worktree.
- It is stronger than the old test: it rejects any installed file without a current source file, compares the text of every Python module, and requires the full set of current modules.
- `installed-stale-guard.log` shows it ran from a temporary site-packages install and passed, not skipped. The PowerShell `NativeCommandError` line there is only unittest writing to stderr.
- I did not inspect `1eb10a1f` itself.

## Findings
- **T1-D2R (defect, test conservation; owner Agent250; origin PR 213/214):**
  - The old AppServer test asserted the controller-level result `('cancelled','cancel_native_unconfirmed')`.
  - In the current code, that conversion happens in `CodexController.prompt`, at `controller/service.py:290-306`: with no terminal native event and exactly one `turn/started`, a cancel gives status `cancelled` with the safe error code, and `turn_timeout` gives status `timeout`.
  - `:330-333` maps a cancelled run with a terminal status other than interrupted or completed to the same pair.
  - Neither branch has a test.
    - The new test stops at the shared session.
    - `test_acp_controller.py:142-164` covers only an interrupted completion.
    - The lifecycle and request-identity tests swap in a fake transport, so the real controller never runs (`test_lifecycle.py:1776`, `test_request_identity.py:48`).
  - Required replacement, in `test_acp_controller.py`, with the session prompt appending a `turn/started` event for `native-thread` and then raising the safe code:
    - cancelled run → `CodexTurn(turn_id, "cancelled", "cancel_native_unconfirmed")` with `interrupt_acknowledged` False;
    - timeout → `("timeout", "turn_timeout")`;
    - a cancelled run whose terminal status is neither interrupted nor completed → `cancelled` / `cancel_native_unconfirmed`.
  - No source change is implied.
- **T2-I1 (two-line scan change in `test_shared/test_git/test_command.py:194-219`): a real fix, with a correction.**
  - The claim that both packages exist in Agent250 doesn't hold.
  - In Agent250 and in c8ccb5f8, `src/laomedo/agents/workspace/` has no Python files; all 11 modules are under `agents/workspaces/`. Only Shared255 has the singular `agents/workspace/`.
  - So before this change, the Agent-specific scans found nothing and the guard was silently empty. Scanning both is correct while the Shared and Agent layouts are reconciled. I didn't check whether ignore rules hide any files.
  - **T2-I1-Q1 (question):** please confirm the package layout above for Agent250.
  - **T2-I1-S1 (suggestion):** neither scan checks that it found any files. A future move could empty them again, which is the failure `test_boundaries.py:24-34` already guards against elsewhere.
  - **T2-I1-S1 (suggestion), continued:** the dropped check that `agents/workspaces/git.py` must not exist is only partly covered by the retired-name scan.
- **T1-D1-S1 (suggestion, not blocking):** `test_boundary.py:31-37` is titled "without claiming termination" but never checks `termination_verified`. The source doesn't set it, so nothing is lost today.

## Verdicts
- **Implementation / test fidelity:**
  - APPROVE for T1-D1, T1-D3, T1-D5, T1-D6 and the T2-I1 change.
  - REQUEST CHANGES, narrowly, for T1-D2 until T1-D2R is covered.
  - T1-D4 is withdrawn.
- **Specification / visual:** not applicable. These are test-only changes with no source, UI or graph impact, and internal controls are not provider or browser acceptance.

## Excluded and still open
- **Excluded:**
  - Findings 217 and 233.
  - The non-Python packets, including the TypeScript adapter's own preflight command set.
  - Provider, browser and live checks.
  - The T1-S suggestions.
  - Hosted Black results, which I didn't see.
- **Updated ledger:**
  - Closed: T1-D1, T1-D3, T1-D5, T1-D6.
  - Withdrawn: T1-D4.
  - Still open: T1-D2R, T2-I1-Q1, T2-I1-S1, T1-D1-S1, T1-S1–S3, C4-S1/S2, C5-S1–S3, C6-S1, and the OpenCode config literal gap.
- **tests-2 status:** I've read the whole batch (1-200, 201-400, 401-600, 601-800, 801-1000, 1001-1200, 1201-1205), but haven't finished classifying its groups. It stays **BATCH_TESTS_2: INCOMPLETE**, apart from the T2-I1 note above.

All-23 remains HOLD, and nothing here authorizes a merge or closure.