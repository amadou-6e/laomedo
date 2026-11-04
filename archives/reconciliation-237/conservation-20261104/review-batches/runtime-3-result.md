**BATCH_RUNTIME_3: COMPLETE.** I found no conservation gaps in this batch. Every change is either preserved behind a canonical model, an intentional supersession, or a stricter behaviour with its own test. One item from batch 2 is still UNVERIFIED and no new ones arose. This covers this batch only; all 23 old PRs stay on HOLD.

**Ranges actually read** (each as a separate bounded read): 1–200, 201–400, 401–600, 601–800, 801–1000 and 1001–1152. That covers every header in the batch, including the repeated class-level and method-level versions:
- **PR 214:** Claude `_execute`; `CodexController` (class, `__init__`, `prompt`, `close`, `_close_resources`); Codex `_execute_acp`; OpenCode `models`, `history_reader`, `run`, `_run_acp`; `Runner` (no owner).
- **PR 216:** the shared `project`; `BaseAgent` (class, `_turn_available` with no owner, `_materialize`, `_prepare`, `_async_worker`, `select_artifacts`); `ClaudeTelemetry` and its `__init__`; `ClaudeAgent` (class, `_mirror_host_login`, `_check_auth`, `_communicate_acp`, `_execute`); `mirror_login`; `ClaudeContainer` and `.client`; `export_rollout`; `CodexAgent` and `_open_server`.

## Results by contract group
| Group (batch lines) | Verdict | Evidence in combined c8 |
|---|---|---|
| Claude `_execute` and `_communicate_acp`: "unknown after dispatch", attempt record, correction loop (2–54, 584–800) | **PRESERVED**, and stricter | A failure after the prompt is sent now gives status `unknown` instead of `failed` and clears `answer`/`native_answer`. Tested in `test_claude/test_runner.py:213-235` and `test_session.py:83`. The attempt record (`to_claude_record`) keeps its field order, pinned by the literal `test_claude/test_records.py`. `_turn_available` is removed as intended; the correction prompt still says "Do not repeat any action". The resume no-replay of buffered events stays **UNVERIFIED**, as I noted in batch 2. |
| `CodexController` startup, prompt and close (56–216) | **PRESERVED**, and stricter | The same codes, now with failure records attached. A natively completed turn without an ACP `end_turn` becomes `unknown`/`runner_runtime_unknown` (tested at `test_codex/test_acp_controller.py:119`). |
| Codex `_execute_acp` (218–347, 994–1135) | **PRESERVED** | The control flow matches the old native `_execute` I mapped in batch 1. The answer is now scoped to the active thread (`_answer(..., thread_id)`). Failure records are kept per attempt (`_retain_attempt_failure`), and lease-result cleanup is normalised through `LeaseCleanupObservation`. |
| OpenCode `models`/`history_reader`/`run`/`_run_acp` (349–401) | **PRESERVED**, and stricter | Receipts are tracked, cleanup is mapped separately from startup, and there is an extra `opencode_cancelled_before_dispatch` check after model configuration. |
| PR 214 `Runner` with no owner (403–405) | **PRESERVED** | The change was `_freeze_workspace` plus `_verify_protected_mounts` (`pr-214.diff:9612-9652`). The current equivalent is `base/agent.py:677-694`, called from the Codex, OpenCode and Claude agents. |
| PR 216 shared `project` envelope (407–414) | **PRESERVED** in the owning PR, pending c8 | Now built through `ActivityProjection.to_payload()`. Key order and output bytes are exactly what you report restored in a29ce61b. I haven't rechecked that here; it belongs to the test batch. |
| `BaseAgent._prepare`/`_materialize`/`select_artifacts`, model-built records (416–554) | **PRESERVED** | `PreparedRunRecord`, `AgentSkillBinding` and `ArtifactReference` replace literal dicts. The prepared records (empty and with a skill, key order and status read) are pinned by the restored `test_runtime/test_preparation_records.py`, which I reviewed against `original-agent-records-a9317f6.json`. |
| `_turn_available` (440–498) | **INTENTIONALLY_SUPERSEDED** (removed at your request) | Per-run `_reserve_turn` stays. |
| `_async_worker` (526–541) | **PRESERVED**, and stricter | It now catches every exception (not only `RunnerError`). A run already in `running` becomes `unknown` rather than being left running, and the snapshot and answer fields are cleared. The fallback code `runner_runtime_unknown` is catalogued and tested. |
| `ClaudeTelemetry` environment (556–581) | **PRESERVED** | Pinned by the literal `ClaudeTelemetryEnvironment` test. |
| `mirror_login`: CLI replaced by py-docker (801–894) | **PRESERVED**, and stricter | Local-only endpoint (`auth/utils.py:52-63`; the npipe spelling is narrowed). Profile volume label check. Admission and a 32 KiB limit (`auth/models.py:37,70-97`). Blank `refreshToken` (`:111`). The writer refuses to overwrite a refresh-capable login and writes 0600 (`resources/write_login.py:27,44`). Container hardening is kept: no network, all capabilities dropped, no-new-privileges, read-only filesystem, pids/memory/CPU limits, tmpfs. Tests: `test_claude/test_login.py:25-266` (remote context, host and pipe refusal; access-only copy; preserved refresh ownership; catalogue coverage), `test_login_session.py:23-260`, and the literal `test_access_login_record.py:13-76`. |
| `ClaudeContainer`/`client` deadline (896–977) | **PRESERVED** | Same as batch 1 (only deadline additions). |
| `export_rollout` (980–991) | **PRESERVED**, and stricter | Adds `--network=none` and uses the image ID instead of the tag. |
| `CodexAgent`/`_open_server` (994–1008, 1137–1151) | **PRESERVED** | The `CodexLaunch` construction is equivalent; only the keyword spelling changed. |

## Findings
- **No new GAP or Low findings.**
- **Carried forward from batch 2 (UNVERIFIED):** no test asserts that a Claude resume skips replaying buffered native events. `test_claude/test_session.py:83` only asserts `_prompt_dispatched`; I didn't open that test body.

## Not inspected
- `test_claude/test_session.py` beyond the grep match.
- `_retain_attempt_failure` persistence tests and the `AttemptFailureRecord` field order.
- The body of `base/agent.py` `_freeze_workspace` (I checked call sites and PR 214's added version only).
- The `PreparedRunRecord.for_preparation` source. It is relied on through the restored literal record test.

This completes the batch as a reading of these PR 214 and 216 runtime definitions. It doesn't make any PR retirable on its own: the remaining runtime batches and all test-delta batches are pending, and the retirement verdict for all 23 PRs stays HOLD. I ran nothing; no models were executed.
