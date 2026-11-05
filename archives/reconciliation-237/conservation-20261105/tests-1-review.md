I've finished the tests-1 batch: all 56 header entries are classified. Most contracts are preserved or intentionally superseded, but six narrow gaps need replacement tests in the owning heads.

**BATCH_TESTS_1: COMPLETE.** This is not an all-23 verdict or feature acceptance. All-23 stays HOLD, and nothing should be merged or closed on the basis of this batch.

## Ranges read
- **1–1000:** read earlier in this session, as 1-200, 201-400, 401-600, 601-800 and 801-1000.
- **1001–1209:** read in this turn as a single call, which covers both 1001-1200 and 1201-1209.
- I also searched the file for every `### ` header to confirm the count: 56 entries.
- **Prior versions:** three Claude runner methods appear under both PR 213 (lines 31, 63, 86) and PR 214 (lines 1147, 1170, 1184). Both versions of each lead to the same current body, so they are classified together below.

## Contract groups
Evidence is in the Agent250 head (`.tools/agent-refactor-205`) unless another path is given.

| # | Entries (tests-1 line) | Status | Evidence / scope |
|---|---|---|---|
| G1 | Claude login/runner: 2, 18, 31, 63, 86, 1147, 1170, 1184 | PRESERVED | `tests/test_agents/test_claude/test_runner.py:485,518,579`. Only the `cleanup_exact` patch target moved, to `claude.agent`. The retired-CLI `Popen` guard is kept. |
| G2 | Codex docker preflight: 106, 116, 127 | PRESERVED | `test_codex/test_docker_preflight.py:109,206` |
| G3 | AppServer reader/session originals: 141, 169, 183 | INTENTIONALLY_SUPERSEDED (ACP) | See the G3 notes below the table. |
| G4 | Retirement/catalogue: 212, 231, 251 | PRESERVED | `test_codex/test_native_session.py:91-113`, `:115-159`, `:185-192` |
| G5 | Leases: 262, 304, 318, 336, 354 | PRESERVED | `test_agents/test_leases/test_supervision.py`, `test_host/test_leases/test_service.py`. Argument order and patch targets moved. |
| G6 | Dependency pin: 278 | PRESERVED | `test_agents/test_architecture/test_dependencies.py` (only `repository_root()` changed) |
| G7 | Mailbox: 368, 392, 407 | INTENTIONALLY_SUPERSEDED (exp only) | `tests/README.md:45` says the prototype mailbox contracts remain historical. The capability-redaction assertion survives at `test_codex/test_acp_controller.py:177-194` and `test_runtime/test_lifecycle.py:373`. |
| G8 | LocalRunner lifecycle: 427, 494, 509, 548 | PRESERVED | `test_runtime/test_lifecycle.py`, now also asserting effective model/effort source. Grant binding at `:1152`. |
| G9a | Unverified container removal: 602 | PRESERVED | `test_acp_controller.py:226-232`, `test_native_session.py:64-85` |
| G9b | Interrupt then remove container: 575 | Mostly PRESERVED, one GAP (T1-D2) | Matching-interrupt contract: `test_acp_controller.py:142-164`. Cancel is forwarded and the terminal response awaited: `test_protocol/test_session.py:146-162`. Health failure triggers cancel: `:195-216`. The `cancel_native_unconfirmed` path has no test. |
| G10 | Native commands: 622 | PRESERVED | `test_codex/test_native_commands.py`, with resources moved to `host/mediation/resources/` |
| G11 | Managed worker: 644 | INTENTIONALLY_SUPERSEDED (exp only) | `experiments/exp104/native_managed_probe.py`. Production grant/ownership: `test_lifecycle.py:1152`. |
| G12 | OpenCode boundary: 672, 686, 713 | PRESERVED | The broker-close assertion left the auth-mount test because `sessions.open` no longer runs in the constructor. It is now at `test_opencode/test_boundary.py:156-184` and `test_runtime/test_failure_finalization.py:76-104` and `:141-158`. |
| G13 | OpenCode cancel: 730 | Value change INTENTIONALLY_SUPERSEDED; path GAP (T1-D1) | The False acknowledgement matches the source: `agents/opencode/agent.py:695-701` says an acknowledgement is not proof of termination. The test no longer reaches that path. |
| G14a | Precheck equals final validation: 769 | PRESERVED except one dropped assertion (T1-D3) | `test_interface/test_output.py`, `test_acp_controller.py:196-224` |
| G14b | Precheck answered before turn ack: 792 | INTENTIONALLY_SUPERSEDED; wire-level ordering UNVERIFIED (T1-S2) | `test_session.py:73-91`. The hook is wired at `codex/controller/service.py:157`. |
| G15 | Installed package has no retired modules: 811 | GAP (T1-D4) | Absent from the tests of c8, Shared255, Agent250, Skills254 and GitHub249. |
| G16 | Provider docker recovery: 821 | Partly PRESERVED (T1-S1) | `test_native_session.py:115-159`, `test_shared/test_errors/test_catalogue.py:217-237`. Original read via the exact path `originals/pr-213/tests/test_provider_docker_recovery.py:124-137`. |
| G17 | Sandbox: 839, 869, 891, 909, 925, 941, 954, 968 | PRESERVED except the `sh -c` argv assertion (T1-D5) | `test_codex/test_sandbox.py:60-81` and the related tests |
| G18 | Settings: 982, 998, 1031 | PRESERVED | `test_shared/test_architecture/test_settings.py:45-81`, `:107-126`, `:170-188`. The negative guards on the retired `split/server.py` are correctly gone. One minor guard was dropped (T1-S3). |
| G19 | Native stream settings: 1010 | Partly PRESERVED (T1-D6) | `test_settings.py:83-105` checks the `ValidationError` cases for both fields. The `Settings.load()` mapping is untested. |
| G20 | Langflow Codex component: 1052 | PRESERVED | Fixture moved to `test_examples/data/codex.json`; the probe moved into the payload. |
| G21 | ACP boundaries: 1085, 1101 | PRESERVED and extended | `test_protocol/test_boundaries.py`. The retired set now also lists `opencode_events` and the projection module. |
| G22 | Provider bindings: 1118 | PRESERVED and extended | `test_protocol/test_provider_bindings.py`, plus a cancel-during-setup case |
| G23 | ACP completion observed: 1198 | PRESERVED | `test_acp_controller.py:74-94`. The new `end_turn` return is required by the stop-reason contract at `:96-122`. |

**G3 notes:**
- **UTF-8 across frames:** now owned by py-docker, at `py-docker/test_suite/test_sessions.py:46-65`.
- **Stderr redaction:** no longer needed, because stderr is discarded rather than stored (`base/acp/transport.py:37-38`, test at `test_session.py:331-337`).
- **Native-event redaction:** `test_acp_controller.py:177-194`.
- **Start-failure cleanup:** `test_native_session.py:64-85` and `test_session.py:122-133`.
- **Deferred release:** `base/acp/session.py:201-204` and `test_session.py:122-133`.

**Finding 233 is settled as PRESERVED.**
- `data/projector-records.json` contains exactly the eight case names listed in `resume-20261105/projector-literal-fidelity.json`.
- That file reports 8/8 matches of input, kwargs, key order and JSON at head a29ce61b.
- `test_envelope.py:21-32` asserts both the key order and the exact `json.dumps` output.
- `final-installed-projectors.log` shows 6 tests OK.
- Caveat: I couldn't recompute the base64 or SHA256 values with read-only tools. This is internal compatibility evidence, not a model/provider claim.

Finding 217 is not in this batch.

## Findings
- **T1-D1 (defect), OpenCode bound-session cancel path is untested.** Owner: Agent250. Origin: PR 213, carried by the ACP move.
  - In the test, `AbortedBackend.run` never calls `on_session`, so `thread_id` stays empty.
  - `cancel()` therefore returns early at `agent.py:687-693`, and the backend's cancel at `:694` is never reached.
  - The run is unblocked by the test's own `finally` (`test_runner.py:448-450`), not by cancelling.
  - `agent.py:694-701` and `boundary.py:586-589` (`broker.stop`) have no test.
  - Replacement: bind a session before blocking, then assert that cancelling unblocks the run, with `cancel_acknowledged` False and `termination_verified` False.
- **T1-D2 (defect), the cancel grace-expiry path is untested.** Owner: Agent250. Origin: PR 213/214.
  - The original asserted `cancel_native_unconfirmed`.
  - Its ACP equivalent, `session.py:168-173`, has no test; `cancel_native_unconfirmed` does not appear anywhere under `tests/`.
  - Replacement: a prompt that never returns after cancel, with `time.monotonic` patched past the 5-second grace, expecting `cancel_native_unconfirmed`, plus the `turn_timeout` variant.
- **T1-D3 (defect), the `dynamic_tool` type assertion was dropped.** Owner: Agent250. Origin: PR 213.
  - `docker/codex-acp/LaomedoExtension.ts:12-17` uses a strict schema that requires `type: "function"` and exactly four keys.
  - `test_output.py:14` imports `dynamic_tool` but never calls it.
  - Replacement: assert the keys and `type == "function"` for `dynamic_tool(pin)`.
- **T1-D4 (defect), the installed-wheel stale-module guard is missing in every head.** Owner: Shared255, which should confirm whether this was intended. Origin: PR 213.
  - Only specific retired-file checks remain.
- **T1-D5 (defect), the split preflight argv is unguarded.** Owner: Agent250. Origin: PR 213.
  - The current test mocks the whole server, so it can't catch a change to the probe commands.
  - The fixed commands are at `codex/controller/service.py:348-366`.
  - Replacement: unit-test `CodexController.preflight` with a mocked executor. Assert:
    - the four permission checks pass fixed `['sh','-c',…]` argv;
    - an unknown check raises `permission_preflight_failed`;
    - non-split mode uses the `laomedo/preflight` extension.
- **T1-D6 (defect), the settings error mapping is untested.** Owner: Agent250. Origin: PR 213.
  - `codex/controller/settings.py:47-64` maps invalid values to `runner_transport_configuration_invalid`; no test covers this.
  - The `ValidationError` half is covered at `test_settings.py:83-105`.
  - Replacement: assert that each invalid value raises `RunnerError('runner_transport_configuration_invalid')` from `Settings.load()`.
- **T1-S1 (suggestion), leftover provider-recovery guards.** Owner: Agent250. Origin: PR 213.
  - No static check now stops `subprocess.Popen`/`run` from being added to `claude/container.py`, `claude/agent.py`, `opencode/boundary.py` or `opencode/utils.py`.
  - `claude/agent.py:44` already imports `subprocess`, but only for `SubprocessError`.
  - `workspace_command_output_too_large` isn't checked as routable, and the four codes aren't checked for non-empty catalogue fields.
  - Current source is fine: `component.py:127,134,169,215` routes all four codes.
- **T1-S2 (suggestion), precheck during a prompt at SDK level.** Owner: Agent250.
  - Add an in-memory wire case, like the one at `test_session.py:260-324`, in which the agent sends `_laomedo/outputPrecheck` before the `session/prompt` response.
- **T1-S3 (suggestion), dropped raw-environment guard.** Owner: Shared255/Agent250.
  - The `assertNotIn('os.environ', …)` check on `claude/container.py` was dropped.
  - The source is clean today.

## Carried ledger
- **Earlier batches:** C4-S1, C4-S2, C5-S1, C5-S2, C5-S3, C6-S1.
- **OpenCode config literal:** tools/share/autoupdate are still unasserted. This remains a possible narrow gap, not a demonstrated defect.
- **This batch:** T1-D1 to T1-D6 and T1-S1 to T1-S3.

## What I couldn't inspect or confirm
- **No test runs:** I didn't run any tests. Apart from the projector log you provided, statuses come from reading test bodies.
- **233 hashes:** not recomputed, as noted above.
- **py-docker:** the UTF-8 evidence comes from the untracked repo-root `py-docker/` copy, not a pinned owner head.
- **Heads checked:**
  - Most groups were verified only against Agent250.
  - c8 was checked only for G15, G18 and G19.
  - I checked the other heads only for G15, and develop not at all.
- **Search coverage:** one broad search across `.tools` timed out, but the narrower searches of each owner head did complete.
- **Original source index:** among this batch's sources it lists only `test_provider_docker_recovery.py`. I read that file at its exact path. The other original bodies are included inline in tests-1.txt.