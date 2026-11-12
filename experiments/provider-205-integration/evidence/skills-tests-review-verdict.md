# Skills ownership closure and test-integration review (d3d06e3a, plus f38e4b70 and 3150ce03)

**Bottom line:** the tests do protect the current contracts, with one exception: an ownership test now silently skips the Agent workspace Skill targets because of a misspelled module prefix (T-01). It is low severity and only affects a test, not production code. The Skills ownership gap is closed. One question remains about a settings test that now checks fewer fields. Nothing here approves a merge, and the docs/maps/deployment packet is still pending.

## 1. Skills ownership: closed

I checked this using the equivalence evidence rather than re-reading unchanged code:
- `skills-develop-equivalence.json` marks 14 files as identical to intended develop 6077e79a. I did not re-read those bodies; I relied on the supplied hashes.
- I read all of `skills-own-imports.diff`. The four "imports only" files (`history.py`, `store.py`, `registry/utils/inspection.py`, `registry/utils/policy.py`) only split grouped imports onto separate lines. They import the same names from the same defining modules.
- The flat `operations/models.py` is absent in both intended develop and the final tree.
- Callers I had already read (`service.py`, `manual.py`, `sources/*`) bind to the defining owners. The `MAX_*` constants now come from `registry.settings`, which is identical to develop.
- Q-I2 is settled: `pyproject.toml:14` declares `"truststore==0.10.4"` as a core dependency.

## 2. Test integration

### Confirmed finding

**T-01 (low, test-only): an ownership control silently skips the Agent workspace Skill targets.**
- **Location:** `tests/test_shared/test_migration/test_shared.py:26` (tests.diff line 3654).
- **Mechanism:**
  - The merge changed the filter prefix from `"laomedo.agents.workspaces.skills."` to `"laomedo.agents.workspace.skills."` (singular).
  - Every real target in `tools/migrations/symbol-paths.json` is the plural form, for example `"laomedo.agents.workspaces.skills.utils"` at lines 156, 222, 249, 418, 1035 and 1090 (23 occurrences).
  - So those targets drop out of `test_skill_relocation_targets_resolve_to_declared_definitions`.
  - `assertTrue(targets)` still passes because the `laomedo.skills.*` targets remain, so the test stays green while checking less.
- **Trigger:** none needed; the skip happens on every run.
- **Impact:** test only. If a workspace Skill owner symbol moved, nothing would catch it.
- **Fix:** restore the plural `workspaces`. This looks like a stray rewrite by the import helper.

### Material question

**Q-T1: the settings test now checks fewer fields.** In `test_settings.py`, the environment-integer check now skips any `int`/`float` field whose `validation_alias` is not a string (diff lines 2784-2786). The intent is clearly to exempt the new CLI-only `launch.settings`, which is also handled separately at diff lines 2768-2775. But the new condition applies to every settings class.
- **Question:** does any existing `int`/`float` field in another settings class lack a string alias, and is it now silently unchecked?
- **Suggestion:** narrow the skip to `launch.settings` only, or assert the expected set of `checked` fields.

### Other changes checked, no issue found

- **Binding corrections in f38e4b70:**
  - Every patch now targets the name in the module that consumes it: `local_launch.*`, `launch.fetch`, `grants._host_principal`, `patch.object(entry, "MediationStore"/"make_grant_bundle_freezer")` and `managed_service.*_main`.
  - The authority assertions are unchanged: operator mismatch, stale content, the grant being required, and no real fetch or HTTP.
  - The runner CLI assertion now expects `agents.agents.codex.cli`. The merge commit asserted the retired path, so that test was red at d3 and is corrected at f38e4b70.
- **Git credential helper path:**
  - The test binds `credential_helper.__file__` under its own alias, so there is no `__file__` shadow.
  - It resolves to the same file as `GitCommandRunner`'s `Path(__file__).with_name("credential_helper.py")`.
  - The removed `runner_module` import is unused; only the aliased `_json` remains.
- **PRContext and routing:**
  - The single `pr_context` port is enforced.
  - Failed or unknown contexts are refused before the gateway or HTTP is called, and nothing is written.
  - No grant is replayed from Data, and an extra feedback consumer is refused.
  - Coverage for the removed `merged_at="now"` case is kept by the new merged-metadata tests, which use the invalid timestamp on an open PR.
- **Profile admission, auth and boundary:**
  - These are fail-closed, with no PIN echo.
  - Internal-actor tokens and API keys are refused.
  - Every upstream user-mutation route returns 403.
  - The tests are labelled internal and are not presented as acceptance.
- **HTTP:**
  - The REST default checks for `CERT_REQUIRED`, `check_hostname` and `NoRedirect`.
  - The redirect-owner inventory now points at `host/http.py`.
- **Retirements:**
  - The migration-tool tests (`test_bytes`, `test_paths`, legacy contract, migration targets, src saved flow, and the migration halves of the GitHub/Shared/Agent tests) were removed, as authorized.
  - The concrete adapter guard is kept: `test_concrete_codex_adapter_refuses_subclass_before_provider_contact` still checks that no HTTP call is made.
  - A historical refusal check is kept (`load_retained_shared` → `refuse_private_git_api`).
  - `load_owner_maps` reads only static JSON and loads no rewriter.

## Coverage

**`tests.diff`, read:**
- lines 1–181 and 288–2440;
- lines 2568–2860, but only the header and opening lines of the two deleted files there (`test_migration_targets.py`, `test_src_saved_flow.py`) plus the start of `test_bytes.py`;
- lines 3102–3121 and 3474–3923;
- lines 4049–4068 and 4291–4307.

**`tests.diff`, not read line by line:**
- lines 182–287: example graph JSON data. I relied on the supplied regeneration record, which I did not read.
- lines 2441–2567 (`test_legacy_contract_migration.py`), 2860–3101 (rest of `test_bytes.py`) and 3122–3473 (`test_paths.py`): bodies of deleted migration tests, header only.
- lines 3924–4048 and 4068–4290: bodies of `test_summary.py` and `test_inspection.py`, new in this diff. I read only their imports, which bind to the current owners; the bodies were not reviewed.

**Read in full:** `test-binding-corrections.diff`, `skills-own-imports.diff`, `skills-develop-equivalence.json`. **Also checked:** grep of `pyproject.toml` and `symbol-paths.json`, and the current `test_shared.py`.

**Not read:** `tests-paths.json`, `tests-combined.diff`, `regenerated-non-code-graph-changes.json`, `graph-digests.json`, `imports-final-unread.diff`, `imports-combined.diff`, `own-stat.txt`.

## Verdicts (this packet only)

- **Skills ownership:** Closed.
- **Tests:** Changes requested for T-01 (a one-word fix). Q-T1 is open. Otherwise the tests protect current behaviour without weakening the auth, grant, routing or streaming checks, and keep no dead migration behaviour.
- **Still pending:** the docs/maps/deployment packet and real owner-graph acceptance. Reviewer status for those: not reviewed, reviewer pending. No merge or issue closure is authorized.