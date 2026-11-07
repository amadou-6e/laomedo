# PR250 at `02c2c291`: Start race fix, spec 403 content and coverage closure

The Start race fix is correct. An in-flight Docker check can no longer silently drop a Start, and an old or failed result never lets startup proceed. The spec 403 content matches the code I read, apart from a stale implementation link. I still can't approve the whole own-diff: a few areas were never read by me as source (listed at the end).

## What I read

- **`start-race-fix.diff`:** lines 1–281, the whole file (README, `models.py`, `prerequisites.py`, `service.py`, `settings.py`, `test_service.py`).
- **`host/runner/service.py`:** lines 106–360, which covers `status`, `_probe_listener`, `_with_docker`, `_offline_state`, `start` and `cancel_start`.
- **Evidence:** `real-start-race.json` and `real-start-race-fixed.json` (both in full).
- **Images:** I opened `recovery-online.png` and `startup-cancelled-final.png`.
- **`spec403-own.diff`:** lines 1–261, the whole file. `agent-protocol.md` is a new file there, so the diff shows all 170 lines. I did not open the copy in the `specs-403-final` worktree separately; I'm relying on the diff matching `55f6ad11`.
- **`prior-review-coverage-index.md`:** lines 1–475, the whole file.
- **Not opened:** `start-race-tests.log`, `recovery-browser-result.json`, `startup-cancellation-final.json`, `spec403-validation.log`, `local-auth-final.log`, `root-usage-final.log`, `verify_start_race.cjs`, the a729 test diff, and `startup.py`. The pass counts and timings below come from your report, not from me.

## Start race fix: no defects

**How the fix works** (`service.py:168-217`):
- **Status polls are still nonblocking.** If another check is running, a poll returns `runner_docker_check_unconfirmed` straight away (`:203-204`).
- **Start waits for the running check:**
  - `start` holds `self.lock` and calls `status(refresh=True)` (`:247-249`). That waits at most `DOCKER_CHECK_TIMEOUT_SECONDS` for `docker_lock` (`:192-194`).
  - Start only proceeds if `docker_observation` is a **different object** from the one it read at `:171` (`:198-200`). An old healthy result, a check that crashed (so nothing was stored), or a wait that timed out all return unconfirmed.
  - It never runs a second check after waiting, so the request budget doesn't grow.
- **Result model:** `DockerReadiness` is strict, frozen and refuses extra fields. It is never serialised. The 5-second timeout has one owner (`settings.py`) and is not configurable.
- **Unchanged:** the public payload shapes and error codes are the same.

**Evidence:**
- `real-start-race.json` attempt 2 shows the mechanism you described: Start returned `runner_docker_check_unconfirmed` while a status check was running, and no process started. As you said, this doesn't establish what happened in the original failed attempt.
- `real-start-race-fixed.json` attempt 2 shows the fix working: both concurrent polls report unconfirmed, yet Start is admitted as `starting`.

**Tests:** the three new tests use a real lock that signals when Start begins waiting. They check that Docker is checked once, and that a process starts exactly once for a healthy result and never for a failed or unconfirmed one, even with an old healthy result cached. These are internal controls, not acceptance.

**Notes (low, no change requested):**
- **Lock fairness:** `threading.Lock` doesn't guarantee who gets it next. A status poll can grab it between the running check finishing and Start getting it. Start then picks up that newer result, still within the 5-second limit. That's correct behaviour, just not strictly "the same check".
- **Timing at the limit:** the wait limit equals the check's own timeout. A check that started just before Start and then times out can push Start to unconfirmed. That is an honest refusal, not a dropped action.
- **Waiting under `self.lock`:** `cancel_start` can wait up to about 5 seconds behind a Start that is waiting. This is bounded, but it's a new possible delay for Cancel.

### Earlier questions now closed
- **A-SB-Q2 (startup cancel race): closed.** `cancel_start` takes the same file lock through `startup_gate(...)` (`:352`), checks for `listening` and only then writes `.cancel` (`:353-357`). Cancellation can't slip in between the server's check, bind and listening steps.
- **A-SB-Q1 (raw error text): closed for this refactor, recorded as an enforcement gap.** I take your word that it is unchanged from base `serving.py:174`; I didn't read base. Error-catalogue and redaction coverage for direct API callers remains an open gap.
- **A-SB-Q3 (missing resume model/effort): closed for this refactor, carried as-is.** I take your word that the controller catches the `KeyError` without exposing the payload; I didn't read the controller's catch.

## Visual check (this fix adds no UI)

**V-Q1 · question · low** (`recovery-online.png`)
- The node header still says "Error details".
- The red-bordered card "The model list could not be loaded" says the runner is online and offers "Refresh models".
- The only green left border is on "Run outcome unconfirmed".
- I can't confirm a distinct green *connection* card from this image. Does the green border belong to the run-outcome card on purpose? Either way this is existing presenter behaviour, not part of this fix.

**V-Q2 · question · low** (`startup-cancelled-final.png`)
- It shows "Docker is ready, but the local runner is not running" with a "Start local runner" button.
- The `startup_cancelled` flag has no visible "cancelled" wording, so a user can't tell this state from an ordinary offline runner. That matches "no new recovery state", but your claim that the flag holds is proven only by the JSON, not by this screen.

## Spec 403 content (`agent-protocol.md`)

I compared the spec with the code I have read:
- **ACP-06, no turn limit:** `_reserve_turn` only counts turns, for diagnostics.
- **ACP-07, raw capture:** the raw-capture behaviour I reviewed is consistent.
- **Usage that never becomes zero or complete when uncertain:** `attempt_usage` returns `None` when a step is invalid and excludes the resume baseline.
- **Cancellation:** Codex keeps its stop-reason reconciliation (C1).
- **Ownership:** py-docker owns containers and the shared client owns cancellation.
- **Unsupported and unknown states:** OpenCode's unsupported output requirements and Claude's undiscoverable skill isolation are both stated honestly.

**S403-D1 · docs correction · low** (`agent-protocol.md:40`)
- It says "Implementation is on draft Laomedo PR #214". It should point to PR250. This is a link fix, not approval of the old #214 stack.

**S403-S1 · suggestion · low** (`:158-170` and front-matter `last_reviewed: 2026-10-29`)
- The evidence section is anchored at checkpoint `9bddf7e`. It could say outright that the final PR250 head has its own separate evidence status.

**S403-Q1 · question · low** (`:102-107`)
- The spec talks about "complete inclusive totals". `NativeHistory.attempt_usage` is root-only, while `ActivityProjection.usage` is described as "inclusive native usage".
- Please confirm that projected usage is never labelled inclusive while child usage is unknown. I haven't traced how `usage` is filled from `attempt_usage`.

**Verdict: SPEC CONTENT APPROVE**, with S403-D1 to fix. This isn't delivered acceptance, a maturity change or a spec merge, and #403 stays a draft. I didn't read the validation log.

## Own-diff coverage

The coverage index is a record of what earlier reviews read; it is not source review. Putting it together with this session's reads, these parts of the own-diff are still **not substantiated by my source reading**:

1. **Migration maps:** `migration-own-current.diff` lines 911–2685 (`module-paths.json` and `symbol-paths.json`) were only grepped. The full `migrate_module_paths.py` was only read partly.
2. **Tests:** the test own-diff beyond these was mostly read by name or through conservation reports, not as source:
   - the 962 correction-test lines and the targeted HTTP and runtime tests;
   - the boundary guard and the campaign wrappers.

   This includes the exp100 S3 test bodies (names only) and the a729 / bb8fa8ca test changes (not read).
3. **Claude provider:** I can't tell from the index that `agent.py` lines 1–194 and 987–994, `utils.py`, `catalog.py`, `cli.py`, `auth/settings.py` and `auth/errors.py` were read. Your statement that the provider-support packets covered "all remaining" provider code would need to cite them.
4. **Codex:** `resources/codex-seccomp.md` was grep-only. The seccomp JSON and LICENSE were excluded by design.
5. **Other areas:**
   - publication handoff `_handoff_gate` (B2) and the Skill store `get`/`read_file` (B3) were never read;
   - packaging (`pyproject`, Dockerfiles) beyond greps;
   - the py-docker pin was not checked;
   - the frontend own-diff beyond the screenshots.

The 162-file AST equivalence shows the code was reused from `8f7b184`, not that it behaves correctly.

## Verdicts

- **Implementation (Start race fix): APPROVE.** No defects.
- **Specification content: APPROVE**, with S403-D1 to fix.
- **Visual: no new UI.** V-Q1 and V-Q2 are open questions about existing behaviour, not full UI approval.
- **Whole own-diff coverage: INCOMPLETE** because of items 1–5 above. This is not a whole-PR approval.

**Still open:**
- the cause of the original failed recovery attempt;
- wheel parity with the new `models.py` (340 files);
- a final full run of the 582-test suite;
- TypeScript still red (259 vs 265);
- the paths not retested: Console/app-owned OAuth, the split executor, child capture, Docker down or uninstalled;
- Claude `evidence_complete` and complete Resume usage are still unknown;
- issues #203 and #215;
- the source grows by 4,675 lines, with no size waiver.

PR250 stays a draft and all 23 old PRs stay on hold. Your final graph approval is still needed, and nothing here authorises a merge.