## Tests-4 conservation batch

**BATCH_TESTS_4: COMPLETE.** All 61 header entries are classified into 29 contract groups. This is not an all-23 verdict or feature acceptance; all-23 stays HOLD, and nothing should be merged or closed from this batch.

Most groups are preserved. Four new narrow gaps came up, all owned by Shared255 apart from T4-D1's GitHub forms. The one with security weight is **T4-D2**: the Skill source policy that excludes secret files (`.env`, credentials, `.netrc`) is now tested only for `auth.json`.

**What I read:**
- All seven ranges of `tests-4.txt`, this turn: 1-200, 201-400, 401-600, 601-800, 801-1000, 1001-1200, 1201-1203.
- The full header list via Grep.
- Root `AGENTS.md` (retained) and Agent250's `AGENTS.md`, which I read by exact path last turn.

**Method:** Read/Grep only. I ran no tests and recomputed no hashes.

**Correction to tests-3:** GitHub249 does have a nested-class and module-alias guard, at `tests/test_github/test_contracts/test_ownership.py:17-37`. T3-S1 is narrower than I said: the remaining unguarded modules are `http/redirect.py`, the host modules, `components/` and `tools/`.

## Group classification
Each path is in the owning head (Shared255 = `.tools/shared-reconciliation-237`, which also holds the Skills tests; GitHub249; Agent250).

| Entries (tests-4 line) | Status | Evidence / scope |
|---|---|---|
| A. No nested classes or module aliases: 2 | Partly PRESERVED (**T3-S1**) | GitHub `test_ownership.py:17-37`; Skills `test_skills/test_interface/test_ownership.py:10-22`; join `test_agents/test_architecture/test_join.py`. No guard for `http/redirect.py`. |
| B. Clients stay leaves; CLI `--help` doesn't start a service: 14, 302 | Mostly PRESERVED (**T4-S1**) | Static dependency direction: Skills `test_ownership.py:10-34`. GitHub CLI `--help`: `test_ownership.py:112-121`. The Skill interface CLIs' `--help` / `--api-token-file` are untested. |
| C. Source guard; handler reply literals: 22, 42 (PR 224 versions) | Same as **T3-D3** | — |
| D. GitHub issue HTTP: 62, 110, 164 | PRESERVED | GitHub249 `test_github/test_interface/test_issues/test_http.py:16,52,112` |
| E. Real stale components: 206 (PR 224 version, adds the `.interface.` rule) | Same as **T2-S1** | — |
| F. Moved-body manifests: 227 (PR 224), 759 (PR 228 later version); template revisions: 341 | INTENTIONALLY_SUPERSEDED (opaque hash manifests) | — |
| G. Migration maps end at the defining interfaces: 238 | GitHub PRESERVED; Skills and CLI rewrite GAP (**T4-D1**) | GitHub `test_ownership.py:53-79` (old modules absent, `MODULE_PATHS`) |
| H. Example patch targets and viewer docs: 261, 456 | GAP (**T4-S1**, plus **T3-D6** for examples) | — |
| I. Partial source-settings migration: 286, 482 (PR 226 adds the mixed `Settings, SKIP` split) | GAP (**T4-D1**) | — |
| J. Changed modules use direct symbols, no nested classes: 315 | Partly PRESERVED by the generic guards | `test_cohesion.py:77-116` |
| K. Maintained example graphs migrate unchanged: 328 | Folded into **T3-D6** | — |
| L. Defining error guard and source policy constants: 365 | GAP (**T4-D2**) | — |
| M. Raw environment boundaries: 378, 421, 776 | Same as **T1-S3** | PR 228 also dropped the "no `os.environ` in `skills/sources`" guard; source is clean today. |
| N. Claude access-login bytes: 398 | PRESERVED | Agent250 `test_agents/test_claude/test_access_login_record.py:13-35` (revision pin, 96 cases, exact bytes) |
| O. Claude mirror codes: 410 | PRESERVED | Same as tests-2 |
| P. Models fields described: 441 | Same as **T3-D2** (extended) | The PR 225 list adds `claude.auth.models` and `host.private_state.models`. |
| Q1. Registry: thirteen function bodies: 501 | INTENTIONALLY_SUPERSEDED (opaque AST proof) | — |
| Q2. Registry split-module migration: 519 | GAP (**T4-D1**) | — |
| Q3. No retired registry imports in callers: 537 | PRESERVED for src; EXP-08 CI INTENTIONALLY_SUPERSEDED | src: `test_shared/test_architecture/test_imports.py:10-38`; `registry/utils.py` absent: `test_skills/test_interface/test_ownership.py:39`. Agent250 `tests/README.md:104-107` says ordinary discovery replaces the EXP-08 campaign run. |
| Q4. Function leaves and model owners: 572 | PRESERVED | `test_cohesion.py:77-90` |
| Q5. Canonical bytes and tree hashes: 587 | Partly PRESERVED (**T4-D3**) | Distinct LF/CRLF revisions: `test_skills/test_registry/test_store.py:470`; `unsafe_relative_path`: `:179` |
| Q6. Registry error producers: 611 | GAP (**T4-D4**) | — |
| R. Workspace skill Git: 641, 675 | PRESERVED (still **T2-Q1**) | — |
| S. Runtime failure observations: 704, 717, 731, 745 | PRESERVED | Agent250 `test_agents/test_runtime/test_failure_observations.py:145,208,248,301` (patch targets only) |
| T. Exception contracts: 798 | PRESERVED (**T4-S3**) | `test_shared/test_architecture/test_settings.py:189-210` |
| U. Source boundaries: 837, 850, 864; utility bodies: 903 | 837-864 PRESERVED; 903 INTENTIONALLY_SUPERSEDED (opaque AST) | Shared255 `test_shared/test_git/test_read_budgets.py:112-142` (now also refuses `clone -u`/`--template`/`--separate-git-dir`), `:229`, `:436`. Behaviour for 903: `test_skills/test_sources/test_service.py:115+`. |
| V. Windows process tree: 927, 941, 955 | PRESERVED | `test_shared/test_git/test_windows.py:101,189,224` |
| W. Lease HTTP handler: 973-1038 | PRESERVED | Agent250 `test_host/test_leases/test_http.py:54-178` |
| X. Production classes not declared inside functions (src, components, tools): 1050 | Partly PRESERVED (**T3-S1**) | Covered only for agents, GitHub and join. |
| Y. Defining imports (host): 1075; lazy composition imports: 1087 | Partly PRESERVED (**T4-S2**) | `test_imports.py:10-38` checks that every eager or lazy import resolves to an owner; nothing bans `import laomedo.x` in host modules or pins where lazy imports sit. |
| Z. Lease client registration: 1100; package root: 1114 | PRESERVED | `test_shared/test_architecture/test_packages.py:53-57`; the README-presence check was dropped (**T4-S2**). |
| AA. EXP-139 verifier reads the real frozen bundle: 1122 | PRESERVED | Shared255 `test_host/test_publication/test_bundle/test_stage.py:33` |
| AB. GitHub ownership: 1144, 1162, 1174, 1192 | 1144, 1162, 1174 PRESERVED; 1192 partly (**T4-D1**) | See the GitHub ownership notes below the table. |

**GitHub ownership notes (AB):**
- **1144 PRESERVED:** repository and label admission at GitHub249 `test_github/test_contracts/test_values.py:140-155`.
- **1162 PRESERVED:** the digest identity and Unicode preimage at `test_values.py:103-112`. Minor: the `contract.pr_digest` attribute and its symbol-map entry are no longer pinned.
- **1174 PRESERVED:** the dispatcher at `test_ownership.py:84-110`.
- **1192 partly:** basic rewrites are at `test_ownership.py:65-79`. The alias, module-attribute and `work_graph.github` forms and the refusals are missing (T4-D1).

## Findings
- **T4-D1 (defect, narrow; owners Shared255 migration tool and GitHub249):** several manual-migration refusals and partial migrations have no test anywhere.
  - Untested forms:
    - `skills.registry.utils` split: `import *`, an unknown member, a bare import, `getattr`, and using the alias as a value;
    - `skills.sources.settings` partial migration: `Settings` moves, `SKIP`/`MAX_ENTRIES` stay, `import *`/`getattr`/fully-qualified uses are refused, and a mixed import is split;
    - `github.issues.utils`: `import *` and `getattr` refusals, aliased and module-attribute forms, and `work_graph.github.validate_repository`;
    - rewriting `python -m <old server>` to the interface CLI.
  - The data and logic exist:
    - Shared255 `tools/migrations/symbol-paths.json:1335-1343`;
    - `tools/migrations/migrate_module_paths.py:121,156`;
    - `tools/migrations/cli-paths.json:9,30`.
  - Grep finds no such test in the tests of Shared255, Skills254, c8, Agent250 or GitHub249.
- **T4-D2 (defect, security policy; owner Shared255; origin PR 224):** the Skill source policy pins are gone.
  - The policy is in `skills/sources/settings.py:5-11`: `SECRET` = auth.json, credentials.json, credentials, `.env`, `.netrc`; `SKIP` includes `.git`; `MAX_ENTRIES` = 4096.
  - It is applied at `skills/sources/bundle.py:40,56` (secret names and the `.env*` prefix) and `local.py:58` / `repository.py:190` (entry limit).
  - Only the `auth.json` refusal is tested (`test_skills/test_sources/test_service.py:115-124`).
  - Replacement: a behavioural `source_bundle_unsafe` refusal for each secret name and for `.env.local`-style files, plus a test of the entry limit.
- **T4-D3 (defect, persisted bytes; owner Shared255; origin PR 226):** registry file-format checks were dropped.
  - Unpinned:
    - `write_json`'s exact bytes (2-space indent, sorted keys, trailing newline; `skills/registry/files.py:56-59`);
    - `read_json` turning a non-object into `invalid_record`;
    - `inventory` raising `missing_skill_file` when SKILL.md is absent;
    - `canonical_json`'s exact escaped bytes (`skills/registry/hashing.py:15-17`).
  - The last is pinned only indirectly, through the hash literals in `test_store.py:514`.
- **T4-D4 (defect; owner Shared255; origin PR 226):** nothing checks catalogue coverage for registry errors.
  - Not checked:
    - catalogue coverage for the `SkillStoreError`/`ConflictError` public codes in `skills/registry/{paths,files,policy,store}.py`;
    - that the runner handler passes `str(exc)` through as `error_category`;
    - that the operation handler collapses errors to `skill_operation_refused`.
  - The existing catalogue tests (`test_skills/test_inspection/test_errors.py`, `test_skills/test_interface/test_errors.py`, `test_skills/test_sources/test_errors.py`) don't scan `skills/registry`.
- **T4-S1 (suggestion):**
  - Skill interface CLIs: `--help` exits 0 and mentions `--api-token-file` without starting a service.
  - Viewer docs: `SOURCE-DEPLOYMENT.md` and `README.md` name `laomedo.skills.interface.sources.cli`.
- **T4-S2 (suggestion):** extend T3-S1 to cover:
  - no `import laomedo.x` in host modules;
  - lazy composition imports staying inside functions (`siwc`, runner routes, managed service);
  - no classes declared inside functions across src, components and tools;
  - the package README exists.
- **T4-S3 (suggestion):** assert that `GitCommandLimitExceeded()` and `GitCommandCleanupError()` default to `cleanup_verified is False` (`git/errors.py:51,63`).

## Ledger and what I couldn't inspect
- **Open:**
  - tests-4: T4-D1 to T4-D4, T4-S1 to T4-S3;
  - tests-3: T3-D1 to T3-D6, T3-S1 (narrowed above), T3-S2, T3-S3, T3-Q1;
  - tests-2: T2-D1 to T2-D4, T2-Q1, T2-S1 to T2-S4;
  - tests-1: T1-D2R-S1, T1-D1-S1, T1-S1 to T1-S3, T2-I1-S1;
  - runtime batches: C4-S1/S2, C5-S1 to S3, C6-S1;
  - the OpenCode config gap (tools/share/autoupdate unasserted).
- **Closed:** T1-D1, T1-D2R, T1-D3, T1-D5, T1-D6 and T2-I1; T1-D4 is withdrawn. 217 and 233 are not in this batch.
- **Not inspected:**
  - test runs and hashes at the reverified heads;
  - the full contents of `data/access-login.json` (I checked only the revision pin and case count in the test);
  - viewer doc text;
  - develop, 1eb10a1f and c8, except for name lookups;
  - Skills254's own test tree beyond name searches (its Skills tests live in Shared255);
  - the GitHub249 catalogue file.

All-23 remains HOLD. Provider, browser, manual-publication and owner merge gates are separate, and no model execution was performed.