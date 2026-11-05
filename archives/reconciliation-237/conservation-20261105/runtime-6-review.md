# BATCH_RUNTIME_6: COMPLETE

All 20 header entries in `runtime-6.txt` are covered, across PRs 222, 224, 226 and 228. Ten contract groups are **PRESERVED** and one is a verified **INTENTIONALLY_SUPERSEDED** (`GitTreeEntry`); there are no gaps or defects. I have one low, optional suggestion. Reading the ranges and finding matching source and tests is coverage, not semantic proof: I ran nothing. This is not an all-23, feature, merge or closure verdict, and the all-23 verdict stays **HOLD**.

**Ranges I actually read from `runtime-6.txt`:** 1–200, 201–400, 401–600 and 601–731.

**Root `AGENTS.md`:** I relied on the section I read earlier (lines 34–49) and did not reread it.

**Entries covered** (class-level entries and their method-level versions were each checked):
- **PR 222:** `SkillOperationServer` and `.__init__`; `source_request`
- **PR 224:** operations `cli.main`; sources `Settings`
- **PR 226:**
  - `inspect_skill`, `validate_policy`
  - `SkillSources`, `._source`, `.discover`, `.revisions`
  - `SkillSources._entries` and `._local_skills`, both marked "no direct normalized owner"
  - `utils._bundle_path`, marked "no direct normalized owner"
- **PR 228:**
  - `GitTreeEntry`, marked "no direct normalized owner"
  - `GitCommand.validate_execution_profile`
  - `source_request`
  - `GitSkillSource`, `._check_cache_budget`, `.entries`

**Owners:** `skills/*` belongs to **Skills254**; `git/*` belongs to **Shared255**. All origins are the listed old PRs. Evidence below is from c8 (`.tools/reconciliation-integration-237`).

## Results by contract group

| # | Contract group (entries) · owner | Status | Current evidence |
|---|---|---|---|
| G1 | Operation server and CLI wire `ManualSkillEditor` with `--manual-permissions` (PR 222/224 server, `cli.main`) · Skills254 | **PRESERVED** | `skills/interface/operations/server.py:8-18`; `cli.py:18-31`.<br>Manual actions are denied by default: `manual.py:27-50` refuses with `skill_manual_not_authorized` when there is no grant or no policy.<br>Tests: `test_skills/test_operations/test_manual.py:46` (denied by default; editor never exposes capabilities), `:240` (private HTTP requires auth; forged editor/authority rejected). |
| G2 | Source client forwards only a bounded `repository_cleanup_unverified` and always closes the HTTP error (PR 222 + PR 228 `source_request`) · Skills254 | **PRESERVED**; the retired proof manifest was replaced by a behaviour test | **Source:** `skills/interface/sources/client.py:55-73`.<br>**Retired:** the opaque proof manifest `tests/contracts/source-client-d2.json` (`pr-228.diff:2461-2474`).<br>**Replacement:** `test_shared/test_git/test_read_budgets.py:436-544` asserts every behaviour the manifest described:<br>• only the exact cleanup code is forwarded;<br>• other categories, malformed, list-typed and oversize (16 385-byte) bodies fall back to `source_discovery_failed`;<br>• a read `OSError` or a close failure also falls back;<br>• the response is closed every time;<br>• `PRIVATE` never appears in the error. |
| G3 | Source settings gain descriptions only (PR 224 `Settings`) · Skills254 | **PRESERVED** | `skills/interface/sources/settings.py:27-52`: same aliases, defaults, `repr=False`/`exclude=True`, and only init and environment as setting sources. |
| G4 | `inspect_skill(include_binary=...)` (PR 226) · Skills254 | **PRESERVED** | Already confirmed in runtime-5: `inspection/utils.py:52, 145`; `test_skills/test_inspection/test_bundle.py:86-222`. |
| G5 | `validate_policy` asset suffixes move to a setting · Skills254 | **PRESERVED** | `registry/settings.py:12` `ASSET_SUFFIXES` is the same seven suffixes as the old literal; `policy.py:64`. |
| G6 | Local source admission, discovery and reading, moved out of `SkillSources._source` / `._local_skills` / local branch of `revisions` into `LocalSkillSource` · Skills254 | **PRESERVED** (logic moved line for line) | `skills/sources/local.py:27-47` (allowed root, link check on every component, `require_exists`, resolved containment), `:49-71` (deadline, exclusions, `MAX_ENTRIES`, depth 16, links, 128 skills), `:73-100` (link check, 128 directories, `MAX_FILES`, bundle path validation, `_read_regular`, total bytes). `service.py:41, 103-105, 110, 197`.<br>Tests in `test_skills/test_sources/test_service.py`:<br>• `:66-89` (immutable history)<br>• `:100-113` (outside paths refused)<br>• `:115-130` (secret file, symlink → `local_source_unsafe`)<br>• `:226-237`, `:264-272` (staging escape, path aliases)<br>Also `test_read_budgets.py:546-564`: the retired private methods are absent, and there is no `Popen`/`killpg` in the `sources` modules. |
| G7 | Repository source moved into `GitSkillSource` (`_git`/`_repository`/`_entries`/`_blob` → `_run`/`repository`/`entries`/`read_blob`) · Skills254 | **PRESERVED** (see C6-S1) | `skills/sources/repository.py:58-212` keeps:<br>• the same argv and protocol policy, now through the isolated profiles;<br>• a 45 s per-command timeout combined with the 60 s operation deadline;<br>• the 128 MiB cache budget;<br>• output caps of 64 KiB, 1 KiB, 2 MiB, 128 B and `MAX_FILE_BYTES`;<br>• the 32-ref limit, path and control-character refusal, exclusions, duplicate refusal and `MAX_ENTRIES`;<br>• the blob mode/kind gate.<br>Tests: `test_service.py:132-187` (branches, tags, pinned prior selection), `:239-262` (no personal or provider environment), `test_read_budgets.py:178-436` (limits and cleanup). |
| G8 | `_cache_bytes`: ignore files that vanish mid-scan; other errors still propagate (PR 228) · Skills254 | **PRESERVED** | `repository.py:37-56`; `test_service.py:37-54` (a lock removed during the scan is ignored), `:56-64` (`PermissionError` propagates). |
| G9 | `_bundle_path` → `bundle.validate_bundle_path` (no normalized owner) · Skills254 | **PRESERVED** (moved and renamed; identical logic) | **Original:** `pr-228.diff:2396-2412`. **Current:** `skills/sources/bundle.py:48-69`.<br>Tests: `test_service.py:264-272`; `test_read_budgets.py:566-615` (callers migrate explicitly; retired helpers are not imported). |
| G10 | `GitTreeEntry` → `SkillRepositoryEntry` (no normalized owner) · Skills254/Shared255 | **INTENTIONALLY_SUPERSEDED (verified)** | The original (`pr-228.diff:474-488`) had three plain string fields — `mode`, `kind`, `object_id` — and left all admission to the consumer.<br>`skills/sources/models.py:93-107` has the same fields and strictness.<br>The consumer gate is unchanged (`repository.py:196-197`), and no `*.py` file in c8 references `GitTreeEntry`. Nothing is lost. |
| G11 | `validate_execution_profile`: option deny-list replaced by a per-subcommand allow-list (PR 228) · Shared255 | **PRESERVED (tightened)** | `git/settings.py:8-16` allows only `--bare`, `--depth=1`, `--no-single-branch`, `--prune`, `--tags`, `--format=%(refname)`, `--verify`, `-rz`, `--full-tree` and `-s`; `git/models.py:183-203`.<br>Every argument the sources pass fits the allow-list, and the clone URL comes after `--`.<br>Rejection tests: `test_read_budgets.py:112-142`. |

## Finding (optional, non-blocking)

**C6-S1 / suggestion / low**
- **Location:** `skills/sources/repository.py:144-145, 184-185, 196-197`. **Owner:** Skills254.
- **Origin:** uncertain; probably a pre-existing gap. These checks were already in the old `_blob`/`_entries`/`_repository`, and the PR 226/228 diffs remove no related test.
- **Issue:** no test exercises:
  - `read_blob` refusing a non-regular tree entry (symlink `120000`, submodule link `160000`, or a non-blob);
  - the 32-ref limit;
  - refusal of tree paths containing control characters.

  The only `read_blob` test is the happy path at `test_read_budgets.py:218`. A grep for `120000`/`160000` under `tests/test_skills` in c8 and `skills-followup-206` found nothing.
- **Consequence:** a regression in the mode gate would let a repository symlink's target text be imported as Skill file bytes, and no test would fail. This is an import security boundary.

## Earlier clarifications, unchanged
- Claude `test_resume_load_receipts_do_not_enter_current_attempt` and the OpenCode config literal gap (tools, share and autoupdate unasserted) are not in this batch. The latter remains a possible narrow regression gap, not a demonstrated defect.
- Findings 217 and 233 were not encountered in this batch.

## Gaps
- **Owner heads:** I didn't compare owner heads to c8 byte for byte. Skills files appear in several develop-based worktrees, so owner attribution is by package.
- **Not available:** there is no `originals/` directory under the audit folder. Original bodies came only from the raw `pr-226.diff` and `pr-228.diff`.
- **Execution:** nothing was run, so there was no live git, HTTP or Windows behaviour.
- **Remaining gates:** full provider/browser/manual publication and the owner merge gates remain separate. No new model execution was performed.