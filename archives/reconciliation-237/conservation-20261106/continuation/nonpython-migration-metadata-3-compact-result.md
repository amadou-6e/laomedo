# nonpython-migration-metadata-3: conservation report (read-only)

**All 23 PRs stay on HOLD.** This report approves nothing. Browser, provider and owner gates are separate.

I accounted for all 16 entries (lines 1-1759).
- **Read in full:** `:1-25`, `:367-513`, `:704-727`, `:1048-1202`, `:1441-1759`.
- **Not read in full:** the symbol-map hunks of PR223/224/226/231 (`:26-365`, `:514-702`, `:728-1047`, `:1200-1440`). I listed their added keys by pattern and checked 23 across all PRs against the current file.

## Inspected ranges (final worktree)

- **Read in full:** `retained-shared-callers.json` (all `path` keys) and `tests/test_skills/test_workspace/README.md:1-26`.
- **Already read earlier:** current `cli-paths.json`, `module-paths.json`, `manual-symbols.json` and `tools/migrations/README.md`.
- **Pattern checks:**
  - the sampled `symbol-paths.json` keys;
  - `experiments/{exp08,exp19}` (no files);
  - `exp08`, `exp19` and `retained-*` references across `tests/`, `src/` and `docs`.

## Dispositions (versions grouped by path)

| Old PR / path | Original change | Disposition | Current evidence |
|---|---|---|---|
| 223 `retained-ingestion-callers.json`, 226 `retained-registry-callers.json`, 231 `retained-github-callers.json`, 238 `retained-http-callers.json` edit (4 inventories) | Per-concern inventories of probe bytes | **INTENTIONALLY_SUPERSEDED** (settled `retained-shared-callers.json`) | Ingestion probes at `:71`, `:162`. GitHub probes at `:13`, `:21`, `:65`, `:106`, `:137`. The `exp08` registry probes and `exp19/live_e2e.py` moved to exp (`tests/test_skills/test_workspace/README.md:5-7`; neither directory is on develop). Stale references remain → D1, plus the open documentation-2 D1 (`host/publication/ingestion/README.md:35`). |
| 223/224/226/228/231/232 `symbol-paths.json` (6 versions) | 223: ingestion → `host.publication.ingestion`. 224: GitHub/Skills clients, servers, handlers, settings and CLIs → `interface`. 226: registry `utils` → `paths`/`files`/`hashing`/`policy`/`diff`. 228: source helpers → `bundle`/`utils`. 231: `github.contract`, `context_reader`, mediated transport. 232: workspace split → `agents.workspaces.{baseline,cleanup,skills}` | **PRESERVED** at the same or later owners, except the handler keys | 19 of 23 sampled keys are present: `:641`, `:643`, `:685`, `:689`, `:1081`, `:1127`, `:1391`, `:1422`, `:1438`, `:1465`, `:1487`, `:1501`, `:1592`, `:1596`, `:1605`, `:1612`, `:1660`, `:1678`, `:1712`. All four `*.handler.*RequestHandler` keys are absent. → Q1 |
| 224 `cli-paths.json` | GitHub/Skills servers and CLIs → `interface.*.cli`; adds `github.issues.cli`, `github.pull_requests.cli`, `skills.{operations,sources}.cli` | **PRESERVED**, except two keys | `cli-paths.json:8-13`, `:23-30`. `github.issues.cli` and `github.pull_requests.cli` are absent, but `module-paths.json:149`, `:159` still rewrite them to the same targets. → S1 |
| 224 `module-paths.json` | 18 GitHub/Skills interface module moves, including 4 `*.handler` modules | **PRESERVED**, except the 4 handler modules | `module-paths.json:149-166`, `:252-284`. The handler entries are absent. → Q1 |
| 232 `module-paths.json` | Removed the `workspace_skills` module maps (namespace split); added `skills.workspace.errors` | **Partly reversed** | `:287` is present. But `:286`, `:288-289`, `:296` re-add module maps for `skills.workspace`/`workspace_skills`. → Q2 |
| 228/232 `manual-symbols.json` (2 versions) | Private `SkillSources` methods refused; `*.workspace_skills` namespace refusals | **PRESERVED** | `manual-symbols.json:30-54` (now naming `SkillRepositoryEntry`, settled); `:73`, `:79`, `:86`, `:100`, `:108`, `:122`. |
| 238 `tools/migrations/README.md` (added) | Declarative file table; retained-inventory policy | **PRESERVED**, rewritten | Current `:1-54`: table `:7-14`, retained policy `:34-43`, hash refusal `:51-53`. The rows for `migrate_module_paths.py` and `migration_errors.py` are gone (`migrate_module_paths.py` is still mentioned at `:16`). → S2 |

## Findings

**nonpython-migration-metadata-3-D1: the registry README claims EXP-08 controls that no longer exist on develop**
- **Applies to:** spec/docs.
- **The claim:** `src/laomedo/skills/registry/README.md:84-86` says "Archived EXP-08 controls run through an explicit temporary import-only migration … supplement current registry behavior tests".
- **The reality:**
  - PR226's `retained-registry-callers.json` was retired, and `exp08` is in neither `retained-shared-callers.json` nor `experiments/`;
  - the campaign is on exp at `3e5f7d7e` (`tests/test_skills/test_workspace/README.md:5-7`);
  - only `tests/README.md:79` mentions it, as archived.
- **Correction:** this revises my documentation-3 disposition of the registry README from PRESERVED to partly stale.
- **Uncertainty:** whether EXP-08's useful assertions were moved into `test_skills/test_workspace` (its README suggests overlap). That is a Python-test question.

**nonpython-migration-metadata-3-Q1: handler mappings from the intermediate interface stage are dropped**
- **Applies to:** implementation.
- **What's missing:** PR224 mapped `github.{issues,pull_requests}.handler` and `skills.{operations,sources}.handler` (module and symbol entries) to `interface.*.handler`. Current has none of these 8 entries.
- **Why it's probably fine:** these handler modules came from the PR222 C1 extraction and never reached develop, so they most likely need no migration.
- **Why it's still open:** saved code built from the intermediate PR branches would now pass through the migrator unchanged. The guard only refuses children of mapped keys (`migrate_module_paths.py:77-89`).
- **Next step:** confirm with the owner that branch-only intermediate names are out of scope.

**nonpython-migration-metadata-3-Q2: the workspace-split module maps PR232 removed are back**
- **Applies to:** implementation.
- **What changed:** PR232 removed the `laomedo.workspace_skills` and `laomedo.skills.workspace_skills` module maps so that callers had to migrate per symbol. Current maps them as whole modules (`module-paths.json:289`, `:296`) to `agents.workspaces.skills.utils`. But functions like `initialize` and `remove_owned_tree` now live in `baseline`/`cleanup` (`symbol-paths.json:1612`).
- **What still protects it:** the symbol map (`:600-640`) and the `getattr` refusal (`:524-531`) likely still route attribute access correctly.
- **Gap:** no test covers the module-level path. This is the open T5-D3 with a concrete current mechanism, not a new defect.

**nonpython-migration-metadata-3-S1: the two maps disagree about the GitHub CLI keys.** Applies to implementation. `cli-paths.json` has `skills.*.cli` keys but not `github.*.cli`. The module map covers the gap, so this is behaviourally harmless. Restoring the keys would make `test_paths.py:263` symmetric.

**nonpython-migration-metadata-3-S2: two files dropped from the migration README's table.** Applies to docs. `migrate_module_paths.py` and `migration_errors.py` were removed from the file table. Optional.

## Leftovers / UNVERIFIED

- I checked 23 of roughly 400 added keys in this packet. Structural coverage comes from `test_shared.py:18-83`, which I didn't run.
- I didn't trace the alias rewrite at `migrate_module_paths.py:300-352` for Q2.
- The contents of exp archives `3e5f7d7e` (EXP-08) and the `exp19` destination.