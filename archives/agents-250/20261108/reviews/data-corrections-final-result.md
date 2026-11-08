I don't recommend closing the data packet yet: about 5,940 of its 8,792 lines are still unread. Nothing I did read shows a confirmed defect, and the five items you asked me to close (Q-S1, Q-S2, Q-P1, the duplicate suite and Q-P2) now each have a disposition. This is not approval of the PR, merging, or retiring the old PRs.

## Ranges read
- **`E/final-dispositions-and-corrections.txt`:** lines 1–644, all of it.
- **Current `tests/test_agents/test_protocol/wire.py`:** lines 1–86, all of it.
- **`E/workspace-conservation-final.json`:** all 8 lines.
- **`E/test-data-final-source.txt`:**
  - **Read:** lines 1–1100 and 1380–1539, then 7204–8792 to the end.
  - **Not read line by line:**
    - 1101–1379: the rest of the `access-login.json` goldens, same generated pattern as 700–1100.
    - 1540–7203: the bodies of the Langflow graph fixtures (`claude-template`, `claude`, `codex`, `controller`, `opencode`). For this range I relied on searches over the whole file instead.
- **Whole-file searches:**
  - Private-data scan (API-key and token prefixes, private-key headers, user home paths, personal email/name): no matches.
  - All 13 `__review_only_full_text_reference__` markers: each points to one of the six printed source sections.
- **Narrow current-source checks:**
  - `components/laomedo/claude_agent.py` imports.
  - `src/laomedo/integrations/langflow/agent/component.py`: a 5-line stable entrypoint that re-exports `AgentComponent`.
  - The `HttpAgentBridge` signature and `bounded_controller.py:107`.
  - Who reads the fixture files (`corpus`, `frozen-flow`, `controller.json`).

## Focused statuses
- **Q-S1: closed.** The only test change from `2e2be4c6` to `e27f1c92` is the 15-line duplicate-key guard (lines 25–51), which I'd already resolved as T-D1.
- **Q-S2: closed.** The supplied evidence (lines 1–24) settles it:
  - The owner is `host/publication/handoff/store.py`. Its diff is one import relocation (`agents.contracts.output` → `agents.interface.output.utils`), and `_handoff_gate` has an identical AST.
  - The `MediationStore` and Skill registry `store.py` blobs are identical on base and head.
  - So the new same-branch handoff test pins existing behaviour. As you said, the earlier nonexistent path was not evidence.
- **Q-P1: closed at internal-control level.** `PrecheckWire` holds back the `session/prompt` response.
  - It sends the real `_laomedo/outputPrecheck` request with the underscore (`wire.py:73-80`). It completes the prompt only when the host's reply comes back on the wire with the right id and no error (82–86).
  - The test asserts:
    - the callback runs while the prompt is pending and before any reply exists (`prompt_id` set, `precheck_reply` None);
    - the exact params that were bound;
    - the reply the wire actually received;
    - `stop_reason == "end_turn"` inside a 3-second `wait_for`;
    - `protocol_failed` is False.
  - This proves the SDK strips the underscore and the request ordering, which the earlier direct `ext_method` call did not. The method matches what the TS extension sends (`LaomedoExtension.ts:82`).
  - `NotificationWire` is the old nested peer moved to module scope, with the same behaviour.
  - Not covered: the real TS↔SDK process boundary, and live Codex.
- **Duplicate workspace suite: closed.**
  - The Skills copy is deleted and the Agent copy keeps all 11 case names (lines 391–644 compared with the Agent version).
  - The Agent copy is the stronger one: it keeps the `base.agent.inventory` baseline-read refusal, which the deleted copy lacks, and now imports `FakeServer` straight from `transport`.
  - Materialization is a 100% rename; READMEs and CONTRIBUTING were updated.
  - The failure in the older shared Langflow environment (`jwt.api_jws` missing) is disclosed and not counted as green, which is correct.
  - One small inconsistency: `workspace-conservation-final.json` says "unchanged except checkout line endings", while git reports similarity 100%. It doesn't matter, but it should say one thing.
- **Q-P2: open as a narrow, known gap; not a defect.**
  - Your description of the structure is consistent with what I've reviewed: `sessionParameters` takes a fixed `cwd=/draft`, accepts one bounded `environmentId` that must equal the host-registered executor, and normal policy can't select one.
  - The old Python ambiguous-list search no longer exists, so there's no ambiguity left to test.
  - Remaining: no dedicated wrong-`cwd` TS case, and live split hasn't been run.
  - Revocation and environment privacy were already settled in the shared packet.

## Data disposition (for the ranges read)
- **Golden expected values:**
  - These include `projector-records`, `status-records`, `prepared-records`, `request-records` and `access-login`.
  - They are characterisation snapshots generated from the current implementation, not independent specs. That's acceptable for regression tests, and the file labels say so (`supporting_internal_synthetic_wire_goldens_only`, `real_credentials_read: false`, `docker_or_model_dispatches: 0`).
  - The useful independent checks are the hostile inputs and the "unknown" status fields:
    - type-confused precheck values become `"unknown"`;
    - usage with a null terminal total becomes `usage: null`, and per-thread usage is null;
    - no price entry gives `amount: null` with a stated reason.
- **Binding:**
  - `access-login.json` binds a source revision, the source file's sha256 and the writer function's AST sha.
  - `component-templates.json` binds the maintained graphs to their canonical component paths and digests.
  - The embedded Claude, Skill and OpenCode sources import `laomedo.integrations.langflow.agent.component`. That is a deliberate stable entrypoint which re-exports the current `AgentComponent`, so it works and is not a stale path.
- **Moved fixtures:**
  - `corpus.json` and `frozen-flow.json` are byte-identical to the accepted-base experiment blobs.
  - `tests/test_work_graph/test_langflow/test_stage.py` and `test_runtime.py` now read the moved copies.
- **Private data:** no matches in the whole-file scan. The tokens are clearly synthetic (`internal-synthetic-access-value`), and URLs are loopback or `host.docker.internal`.

## Confirmed defects
None in the ranges read.

## Questions and suggestions (non-blocking)
1. **`controller.json` binding is unclear (suggestion).** Its embedded `LaomedoBoundedController` source (f4dd…, lines 8579–8660) is a compact, semicolon-joined form that differs from the current `components/laomedo/bounded_controller.py`, although it calls the same thing (`RunnerAdapter(json.loads(self.endpoints_json))`).
   - `component-templates.json` doesn't list it. Its only reader is `test_shared/test_migration/test_paths.py:158`, which uses it as a saved-wire input for the migration `--check`.
   - That's a legitimate use. A one-line label saying "saved-wire migration input, not a current template" would remove the ambiguity.
2. **Base tests still read the experiments tree (unchanged base; not new).** `test_work_graph_launch.py:28` still reads `experiments/exp16/corpus.json`, and `test_timeout_trace.py:15` reads `experiments/exp03/flow.json`, even though the same bytes now exist under `tests/test_work_graph/fixtures/`. Pointing them at the fixtures would remove the last production-test reads of the experiments tree.

## Remaining own-diff gaps
- **Unread fixture bodies:**
  - Lines 1101–1379: generated goldens of the same kind as 700–1100.
  - Lines 1540–7203: the bodies of the five Langflow graph fixtures. For these I relied only on the private-data scan, the reference-marker check and the digest manifest; I did not read them line by line. A further bounded pass can do that if you need it.
- The Q-P2 wrong-`cwd` TS case is missing.
- CI for the new head `e317eb3e` is still pending. The earlier green result is for `e27f1c92`.
- **Not retested:**
  - native GitHub mediation (#215);
  - default Console and app-owned OAuth;
  - the split executor;
  - a new child capture;
  - Docker being down or uninstalled.

  The real-provider and recovery results keep their original revision bindings.
- **Still open:**
  - TypeScript is inherited red (259 vs 265).
  - Spec 403 (`558d7e2`) is still a draft.
  - The owner's graph validation is missing.
  - The 23 old PRs stay on HOLD, with no merge.

The integration verdict comes next and doesn't waive the owner or spec gates.