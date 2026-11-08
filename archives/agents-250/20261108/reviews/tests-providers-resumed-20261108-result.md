I've now read the whole provider test packet. **Verdict for this packet: no confirmed defects.** It moves the tests and replaces the native ones faithfully, but it is all internal-control evidence. It does not approve the PR, merging, or retiring the old PRs.

## Ranges read
- **`E/test-own-providers.diff`:** lines 1–8757 in full, in pages of 700–780 lines (5801–6500, 6501–7200, 7201–7980, 7981–8757). Line 8757 is the last line of `test_runtime/utils.py`.
- **Other files, read narrowly:**
  - `test_catalogue.py` lines 1–40
  - `serve-signature-final.txt` (all of it)
  - `LaomedoExtension.test.ts` lines 1–79
  - searches only in `LaomedoExtension.ts`, `base/acp/session.py` and `codex/controller/service.py`

## Confirmed defects
None.

## Questions (each with its mechanism)
1. **Q-P1: the Codex output precheck has no end-to-end test.**
   - **TS side:** `LaomedoExtension.ts:77-82` filters to `laomedo_output_precheck` and forwards it with `host.request("_laomedo/outputPrecheck", …)`. No TS test covers this; `LaomedoExtension.test.ts` only checks that preflight is closed once a prompt starts.
   - **Python side:** `session.py:225` matches `"laomedo/outputPrecheck"` with no underscore. The test (`test_session.py:75-89`) calls `ext_method` directly with that stripped name.
   - **The gap:** whether the SDK strips the `_` is never checked by a test. The wire-ordering test (`AcpOrderingTests`, diff 5979–6046) only covers the `_laomedo/codexEvent` notification, not a request answered while `session/prompt` is still pending.
   - In `test_lifecycle`, the production `CodexController._precheck` is called from inside the test double's `wait_turn`, so only the validator is tested, not how the request reaches it.
2. **Q-P2: two split-executor tests were removed.** `test_split_selection_refuses_missing_ambiguous_or_wrong_executor` and `test_split_wait_turn_revocation_interrupts_without_completion` are gone (diff 7703–7735). The TS test does check that an unregistered split `environmentId` is rejected (line 38). I found no Python replacement for:
   - rejecting an ambiguous or wrong `cwd` selection;
   - auth revocation interrupting a turn mid-way.

   The split executor is already listed as not retested.
3. **Q-P3 (carried over): environment privacy.** Is there still an equivalent environment-privacy guard now that `test_private_environment_is_not_serialized` is retired? The new checks are `assertNotIn(secret, spec.model_dump_json())` in the mediator-mount and lifecycle tests (7593, 7849), which partly cover it.

## Suggestions (non-blocking)
- `test_recovered_metadata_is_removed_but_run_history_is_preserved` never asserts that the metadata is removed.
- `test_host_budgets_validate_before_launch_attempt_marker` checks the order of text in the source file, not behaviour.
- **Docstrings after imports:** in several moved or new files (`test_accounting`, `test_failure_finalization`, `test_failure_observations`, `test_lifecycle`, `test_prerequisites`), the module docstring sits below an inserted import, so it no longer counts as a docstring.
- The pure-model OpenCode history tests sit inside a class that is skipped when `py_docker` is missing.
- `FakeServer` (`transport.py`) keeps the old native request/wait hooks, labelled as fixture-only. That's acceptable, but every runtime lifecycle result built on it is internal-control evidence only.

## Replacements of the old native controls (checked)
| Old test | Replacement | Verdict |
|---|---|---|
| AppServer interrupt → `docker rm`/`inspect` | ACP cancel waits for the native terminal response; a missing response gives `cancel_native_unconfirmed` / `turn_timeout`; the pending prompt is collected and the container isn't closed (5834–5884); close-order and cleanup-failure tests (5810–5821, 6497–6610) | Correct |
| `wait_turn` for an already-queued completion | Raw terminal notification captured before the prompt returns (5982) | Correct |
| `_docker_prefix` argv strings | Field assertions on `CodexLaunch.to_container_spec()`: read-only capability mount, mediator instance, git `safe.directory` for both images, `cap_drop == ["ALL"]`, `no-new-privileges` | Same or stronger |
| `--resume` argv | `load_session` with the saved ID; no new session; replay discarded (5801–5808) | Correct |

**Mock targets:** all patch the module where the name is used (`codex.agent.cleanup_exact` / `LeaseClient`, `base.agent._json`, `host.runner.service.check_docker`, `claude.auth.utils.mirror_login`), or a lazy `AcpSession` import. I found no wrong targets.

**Skips:** all gate on optional dependencies (`py_docker`, ACP), which the CI runner extra provides.

**New behaviour tests:**
- Failure finalization and observations: the first error is kept, the cleanup fact isn't invented, and the lock is released.
- Lease loss.
- The worker-exception terminal record.
- The in-flight Docker check during Start.
- The supervisor arguments for Codex and Claude.

## Dispositions
- **T-D1: resolved.** The mechanism is a duplicate-key `object_pairs_hook` that fails on any repeated key, not just a renamed test.
- **A-MG-Q2: closed.** The historical `serve` had a loopback-only check plus a startup-gate cancel/listening order, which matches `RunnerServer`.
- **T-Q1: partly answered; remains a question (Q-P1).** The TS side does close preflight once a prompt starts. The routing of the output precheck while a prompt is pending is not exercised end to end.
- **T-Q2: no material regression found.**
  - The Codex activity-parity tests and model-source fields are kept: `effective_model_source` / `effective_effort_source` = `host_requested_adapter_asserted` (7834–7839).
  - The pricing and accounting tests were moved unchanged, apart from removing the obsolete `_turn_available()` calls.

## Remaining gaps
- Q-P1 and Q-P2 above.
- The shared test packet (7,404 lines) and the disposition of the JSON data files (e.g. `data/prepared-records.json`) are not reviewed.
- **No acceptance yet:** this packet is fixture- and double-based throughout. Live acceptance has not been retested for:
  - #215;
  - Console OAuth;
  - the split executor;
  - child capture;
  - Docker being down or uninstalled.
- TypeScript is still red (259 vs 265).
- Spec 403 is still a draft.
- Still open: the integration verdict and the owner's final graph approval.