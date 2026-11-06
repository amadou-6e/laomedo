# BATCH_TESTS_5: COMPLETE

All 26 headers are classified into 24 groups, with evidence for each. Two sub-items are **UNVERIFIED** because their evidence was never exported or would need code execution: G6's file set and G9's bare-namespace behaviour. A few smaller sub-claims also rest only on the grep results I have (G5's components/tools reach, G6's Agent250 manifest and G18's frontend test bodies); I say so in each row. This report uses only inspections already made; I did no new searching.

This is not an all-23 verdict and does not accept any feature. All-23 remains **HOLD**. I ran no models, providers, shell commands, edits or GitHub actions.

## What I read

- **The packet:** `tests-5.txt` in full, in three ranges: 1-200, 201-400 and 401-516.
- **Headers:** I listed them with a header Grep. There are 26 `###` entries, plus one CURRENT CANDIDATE (line 358) and one diff target (line 245).
- **Two versions of one method:** "affected error producers" appears for both PR 232 (line 296) and PR 238 (line 491). I reviewed both. The PR 238 version is the stricter one.
- **Current heads:** c8 = c8ccb5f8; Shared255, GitHub249 and Agent250 are as stated in your request. For Skills254 I only grepped `src`.

## Dispositions

| # | Old PR / test | Disposition | Current evidence |
|---|---|---|---|
| G1 | 231 `test_retained_probe_bytes_and_loader_scope_are_explicit` | **PRESERVED**, with a test-harness gap | **Scope and hash:** `tests/support/retained.py:42-48`. The bytes are pinned against `tools/migrations/retained-shared-callers.json`. Shared255 `test_shared/test_migration/test_shared.py:132-146` checks the inventory hashes.<br>**Adaptation:** GitHub249 and c8 `retained.py:150` rewrite `laomedo.github.*` imports. `experiments/exp100/probe_native_capture.py:30` imports `GitHubMediatedTransport` from the retired path, and `test_native_capture.py:13` loads it, so a broken adaptation would fail at import.<br>**Gap:** no test checks that a non-inventoried name is refused (`retained.py:43`) → T5-S1. |
| G2 | 231 `test_retained_run_injection_requires_manual_full_source_migration` | **PRESERVED** for synthetic sources; the real-file part is **INTENTIONALLY_SUPERSEDED** (experiments are exp-only) | `run=` is refused at GitHub249 `test_shared.py:88-102`. c8 `test_shared.py:94-100` also covers `**options`. |
| G3 | 231 `test_current_producers_keep_catalogue_and_cli_only_errors_distinct` | **PRESERVED**, minor residual | **Codes:** `issues/contract.py:72-74,103-105` and `pull_requests/contract.py:94-96` hold both codes.<br>**Test:** c8 `test_github/test_contracts/test_errors.py:22,36-42`.<br>**Catalogue entries:** `:1572` and `:1582`.<br>The check that the CLI-only message is *not* a catalogue key was not kept → T5-S4. |
| G4 | 231 `test_retired_context_file_and_core_dependency_cannot_return` | **PARTIAL** | **Kept:**<br>- no `import laomedo.` in `github` (GitHub249 `test_ownership.py:32-37`);<br>- retired-path migration (`:65-79`).<br>**Lost:** the guard against `github` importing `work_graph` or `lfx` → **T5-D1**.<br>**Folded into T2-D2:** absence of `issues/utils.py` and of `class GitHubMediatedTransport` in `git/transport.py`.<br>**Not applicable:** `viewer.py`, because `src/laomedo/integrations` is absent on GitHub249. |
| G5 | 231 `test_maintained_executable_imports_use_current_definitions` | **GAP** | `test_imports.py:10-38` only checks that the *module* exists → **T5-D2**. |
| G6 | 231 `test_template_revisions_preserve_every_other_graph_value_and_component_body` | **INTENTIONALLY_SUPERSEDED**; file-set equivalence **UNVERIFIED** | **Replacement:** c8 `test_shared/test_templates/test_sources.py:14-51`. It checks canonical source, that `code_hash` presence matches the manifest, and a hash of the full graph. It is stronger than the old test.<br>**File set:** c8 and GitHub249 `component-templates.json` both cover 7 graphs. The original manifests (`23cb115`: 11 files and 16 nodes; `6656c1c`) are not in `original-source-index.json` or any head, so I could not compare file sets.<br>**Mismatch:** from my earlier `"path"` grep, Agent250's manifest still lists `examples/github-pr/flow.json` (`:75`), which c8 archives (`test_cohesion.py:16-24`). I did not re-check it in this pass. → T5-Q1 |
| G7 | 232 `test_all_five_function_bodies_and_signatures_are_unchanged` | **INTENTIONALLY_SUPERSEDED** (opaque AST and blob proof) | **Symbol maps:** Agent250 `symbol-paths.json:1590-1611`.<br>**Targets resolve:** `test_cohesion.py:26-71` and c8 `test_shared.py:102-121`.<br>**Behaviour:** Agent250 `test_agents/test_workspace/test_skill_exclusion.py:124,139,166-244`. |
| G8 | 232 `test_exception_code_arguments_and_inheritance_are_preserved` | **PRESERVED** by behaviour | **Shape:** `agents/workspaces/skills/errors.py:6-14` (ValueError, `.code`, args).<br>**Code reaches the result:** `test_skill_exclusion.py:124,139`.<br>Direct `isinstance(ValueError)` and `.args` assertions are not repeated; I see this as low risk and raise no finding. |
| G9 | 232 `test_known_split_symbols_migrate_and_ambiguous_namespaces_fail_closed` | **GAP**; bare-namespace behaviour **UNVERIFIED** | → **T5-D3**, **T5-Q2** |
| G10 | 232 `test_preserved_exp104_sources_allow_only_explicit_import_migration` | **PRESERVED** for top-level imports | **Rewrite:** `retained.py:98-118` rewrites the top-level import in c8 `native_localrunner_worker.py:17`.<br>**Old before/after call check, now generalised:** `retained.py:178-201` requires the non-import AST to be unchanged.<br>**Loaded:** `test_native_localrunner_probe.py:5-6`.<br>**Residual:** the function-local import at `native_localrunner_probe.py:625` is not rewritten → T5-S2. |
| G11 | 232 `test_maintained_imports_patch_targets_and_dependency_direction` | **PRESERVED** | **Skills must not import agents, host, github or work_graph:** Shared255 `test_skills/test_interface/test_ownership.py:23-34`. The `src` greps on Agent250 and c8 are clean.<br>**`workspace/utils.py` stays absent:** `:36-51`.<br>**Workspace function files can't add classes:** `test_cohesion.py:73-86` covers this.<br>**Folded into T2-D2:** `workspace/errors.py` absence.<br>**Runtime-checked:** patch-string targets fail when executed. |
| G12 | 232 `test_maintained_callers_have_no_retired_registry_imports` | **`src`: PRESERVED.** **EXP-08 CI: INTENTIONALLY_SUPERSEDED.** **Repo-wide part: carried into T3-D6.** | **`src`:**<br>- `registry/utils.py` is absent, and Shared255 `test_ownership.py:39` checks that;<br>- `test_imports.py` catches any `src` import of it;<br>- maps at `symbol-paths.json:1335-1347`.<br>**EXP-08 CI:** replaced by ordinary discovery (Agent250 `tests/README.md:104-107`). |
| G13 | 232 shared-git diff | **SETTLED** (T2-I1) | Carries T2-I1-S1. |
| G14 | 232 `test_five_function_bodies_preserve_operations_after_direct_imports` | **INTENTIONALLY_SUPERSEDED** | Opaque proof. Behaviour sits in the concern-owned Skill operation suites recorded in earlier batches. |
| G15 | 232 `test_skills_owned_files_have_no_module_prefix_imports` | **PRESERVED** | Shared255 `test_ownership.py:16-22`. |
| G16 | 232 `test_affected_error_producers…` (line 296), the 238 version of the same test (line 491), and 234 `test_affected_producer_codes…` (line 339, CURRENT CANDIDATE) | **PRESERVED**, apart from one unbacked exception | **Replacement:** `test_skills/test_inspection/test_errors.py:11-65`. The inventory JSON is superseded.<br>**Handler fallback `skill_operation_refused`:** checked by behaviour at c8 `test_skills/test_interface/test_http.py:76-78`, using `utils.py:30`.<br>**Exception:** the `{"skill_file_missing"}` exception at `:49` is not backed by any test → **T5-D4**. |
| G17 | 233 `test_projectors_match_frozen_old_writer_bytes` | **SETTLED** earlier | No change. |
| G18 | 234 `test_inline_viewers_share_presenter_and_installer_owns_new_files` | **PRESERVED**; part **INTENTIONALLY_SUPERSEDED** | **Static checks:** c8 `test_skills/test_inspection/test_viewer.py:8-31`.<br>**Jest tests with no Reload/Retry on read failure:**<br>- `SkillFilesModal.test.tsx:45-50`;<br>- `SkillHistory.test.tsx:112`;<br>- `SkillInspectionError.test.tsx:16`.<br>**Jest copy tests:** `ErrorPopup.test.tsx:30-33`.<br>**Superseded by a later feature:** `SkillFilesModal.tsx:278-279` now uses `<ErrorPopup>` for manual edits, and `:184,255,263` add "Retry comparison/edit controls".<br>**Dropped:** the installer-name checks → T5-S3. |
| G19 | 238 `test_private_redirect_alias_is_absent` | **PRESERVED** | **Owner set excludes the REST transport:** c8 `test_redirects.py:51-82`.<br>**Transport uses the public class:** `rest/transport.py:10` imports `NoRedirect`.<br>**Migration:** GitHub249 `test_shared.py:104-122`.<br>The alias-assignment case stays in T3-S3. |
| G20 | 238 `test_maps_end_at_defining_interfaces_and_cli_commands_not_server_classes` | **PARTIAL** | **Kept:**<br>- GitHub module maps (GitHub249 `test_ownership.py:53-64`);<br>- one-pass check (`test_cohesion.py:114-124`);<br>- retired Skill files stay absent.<br>**Not covered — carried in T4-D1:** the `python -m <old>.server` → interface CLI rewrite (`cli-paths.json:9,11,26,30`). The only tested rewrite is `local_runner` (c8 `test_paths.py:269-270`).<br>**Carried in T4-D2:** the special case for `skills.sources.settings.Settings`. |
| G21 | 238 `test_changed_modules_use_direct_symbols_without_new_nested_classes` | **PARTIAL** | **Kept:**<br>- GitHub (`test_ownership.py:17-37`);<br>- Skills (`:16-22`);<br>- mixed class/function check (`test_cohesion.py:73-86`).<br>**Not guarded:** nested classes in Skill interface modules → carried in T3-S1. |
| G22 | 238 `test_component_templates_follow_canonical_source_and_keep_graph_values` | **PRESERVED** (stronger) | c8 `test_sources.py:14-51`. |
| G23 | 238 `test_defining_error_guard_follows_current_interface_sources` | **GAP**, already carried | The source-policy pins are T4-D2 (security). Interface admission is T3-D4. |
| G24 | 238 `test_registry_symbol_map_targets_are_callable` | **PRESERVED**, weaker | **Map data:** all 13 expected entries are at Shared255 `symbol-paths.json:1335-1347`.<br>**Targets resolve:** generically, at `test_cohesion.py:26-71`.<br>**Not pinned:** the exact old→new pairs → T5-S5. |

## New findings

**T5-D1 — defect. Owner: GitHub249.**
- **Lost assertion:** PR 231 asserted that GitHub's core files never import `laomedo.work_graph` or `lfx`.
- **Evidence it is gone:**
  - Greps of `tests/test_github` and `test_shared/test_architecture` find no such guard.
  - Skills has the equivalent guard (Shared255 `test_ownership.py:23-34`); GitHub does not.
- **Current state is clean:**
  - `github/contract.py` has no `laomedo` imports.
  - `issues/context_reader.py:9-10` imports only GitHub modules.
  - A grep of GitHub `src` finds no `work_graph` or `lfx`.
- **Trigger:** a future import of `work_graph` or `lfx` from `github/*` would pass every test.

**T5-D2 — defect. Owner: GitHub249. It extends T3-D6 with new evidence at the symbol level.**
- **Mechanism:**
  - `github/issues/contract.py:3` imports `labels_value` from `github.contract`, so the name is still bound in the old module.
  - The old path `laomedo.github.issues.contract.labels_value` is listed as retired at `symbol-paths.json:485`.
  - So a maintained caller can still `from laomedo.github.issues.contract import labels_value`. That import resolves at runtime and passes `test_imports.py`, which checks modules only.
- **Missing scan:** I found no test that scans maintained callers for retired *symbols*.
- **Unverified scope:** whether `tests`, `components` and `tools` callers are scanned is based on grep alone.

**T5-D3 — defect. Owner: Agent250 for the workspaces, plus the migration tool's owner. It cross-references T4-D1.**
- **Lost assertions:** PR 232 tested two things:
  - known split symbols from `laomedo.skills.workspace.utils`, `skills.workspace_skills` and `workspace_skills` migrate in one pass;
  - `*`, unknown, bare-value and `getattr` forms raise `ManualMigrationRequired`.
- **Evidence they are gone:** greps of Agent250 and c8 `tests/test_shared/test_migration` find no test for these namespaces. The nearest are `test_shared.py:102-121` (targets resolve) and `test_paths.py:207-225` (`local_runner`'s `_hash_tree` only).
- **The map data exists:**
  - c8 `module-paths.json:286,289,296`;
  - `manual-symbols.json:73-122`, including `local_runner.workspace_skills`.
- **Result:** nothing tests that the fail-closed path still refuses these forms.

**T5-D4 — defect. Owner: Skills254 and c8.**
- **The unbacked exception:** the current catalogue test (`test_errors.py:49`) allows `skill_file_missing` to have no catalogue entry. Its comment says the manual HTTP boundary maps that code to `skill_manual_invalid`.
- **Where the code comes from:** c8 `operations/models.py:126` raises it (in `FileEdit.to_bytes`), and so does `service.py:208`.
- **The mapping exists in source:**
  - `handler.py:102,107` maps it to `skill_manual_invalid` (catalogue `:1502`);
  - otherwise `:112` returns `skill_operation_refused` (catalogue `:2077`).
- **Nothing tests that mapping:**
  - `skill_manual_invalid` appears in c8 tests only inside that comment;
  - `test_binary.py:145` checks the error at the service level, not the HTTP projection.
- **Trigger:**
  1. Remove `"skill_file_missing"` from the set at `handler.py:97-103`.
  2. A manual edit whose `source_path` is missing then falls to `skill_manual_unavailable`, because `SkillStoreError` is excluded from the ValueError branch (`:104-109`).
  3. Users see the wrong code, and no test fails.
- **Why the exception itself is legitimate:** the code arrived after PR 238 with the binary-edit feature, so that part is an intentional supersession.
- **Not applicable to Shared255:** its `models.py` does not raise the code, so the exception there is unused.

**T5-Q1 — question. Owners: GitHub249 and Agent250.**
- **Unverifiable comparison:** the original PR 231 manifest set (11 files and 16 nodes) cannot be compared with today's 7 graphs.
- **Uncovered fixture:** `tests/test_agents/test_examples/data/controller.json` contains 5 `code_hash` entries. It is checked only by migration `--check` (c8 `test_paths.py:158-164`), not against the canonical component source.
  - Should it be in `component-templates.json`?
- **Manifest mismatch:**
  - Agent250's manifest still lists `examples/github-pr/flow.json`, which c8 archives.
  - Which of the two is intended?

**T5-Q2 — question. Owner: migration tool.**
- **Old expectation:** PR 232 required `import laomedo.skills.workspace` to raise `ManualMigrationRequired`.
- **Possible change:** c8 `module-paths.json:286` now maps that name to `laomedo.agents.workspaces.skills`, so the tool may rewrite it instead.
- **Why it's unresolved:** I can't settle this without running the tool. Is a rewrite now intended?

**T5-S1 — suggestion.** Add a negative test for the retained loader:
- a name that is not inventoried is refused (`retained.py:43`);
- the adapted `GitHubMediatedTransport` is the canonical class.

**T5-S2 — suggestion.**
- **Gap:** the loader only rewrites top-level imports (`retained.py:98-176`), so the function-local import at `native_localrunner_probe.py:625` still points at the non-existent `laomedo.skills.workspace.utils`.
- **Fix:** document or refuse that path.
- **Unchecked:** I did not check whether any test runs it.

**T5-S3 — suggestion.**
- **Gap:** `test_viewer.py` no longer asserts that the installer ships `SkillFilesModal.test.tsx` (installer `:167`) and `ErrorExplanation.tsx` (`:308`). `ErrorPopup.tsx:2` imports the latter.
- **Effect:** dropping either would only surface in a real Langflow build.

**T5-S4 — suggestion.**
- **Missing negative:** nothing asserts that the CLI-only message "Repository must be owner/name" never becomes a catalogue key.

**T5-S5 — suggestion.**
- **Missing pins:** pin the exact 13 registry old→new symbol pairs.
- **Why:** if a pair were pointed at another callable that exists, the current reachability test would still pass.

## Material I could not inspect

**Original files that were never exported** (they are not in `original-source-index.json` or any head):
- `interface-template-revisions-23cb115.json`
- `github-template-revisions-6656c1c.json`
- `retained-github-callers.json`
- `retained-registry-callers.json`
- the PR 232 `RECORD` data
- `skills-direct-imports-b614cf3.json`
- `skills-direct-import-errors.json`

**Partly read:**
- `retained.py`: I read lines 1-217 on Shared255, but only `:119-178` on GitHub249.
- Frontend `.tsx` test bodies: grep lines only.

**Not read by me:** `tests-5-timeout-inspection.json`.

**Not executed:** nothing was run — no migration tool, unittest or Jest. The Jest and TSX evidence is static code and test coverage only. It is not visual or browser acceptance.

## Ledger (carried forward, not re-investigated)

- **Settled:** T1-D1, D2R, D3, D5, D6; T2-I1; 217; 233. T1-D4 is withdrawn.
- **Open from tests-1 and the recheck:** T1-D2R-S1, T1-D1-S1, T1-S1, T1-S2, T1-S3, T2-I1-S1.
- **Open from tests-2:** T2-D1, T2-D2 (now also covers `issues/utils.py`, the `GitHubMediatedTransport` class location and `workspace/errors.py`), T2-D3, T2-D4, T2-Q1, T2-S1, T2-S2, T2-S3, T2-S4.
- **Open from tests-3:** T3-D1, T3-D2, T3-D3 (G16 found behavioural coverage of the handler fallback, which may narrow its handler-literal part; the owner should confirm), T3-D4, T3-D5, T3-D6 (extended by T5-D2), T3-S1, T3-S2, T3-S3, T3-Q1.
- **Open from tests-4:** T4-D1 (now also covers G20's CLI rewrite and is cross-referenced by T5-D3), T4-D2, T4-D3, T4-D4, T4-S1, T4-S2, T4-S3.
- **Open from the runtime batches:** C4-S1/S2, C5-S1 to S3, C6-S1, and the OpenCode config literal gap.
- **New from tests-5:** T5-D1 to D4, T5-Q1, T5-Q2, T5-S1 to S5.

The real provider, browser and manual-publication gates, and the owner merge gates, are still separate checks. No PR should be merged or closed on the strength of this batch.