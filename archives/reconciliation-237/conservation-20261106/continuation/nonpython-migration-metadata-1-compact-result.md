# nonpython-migration-metadata-1: conservation report (read-only)

**All 23 PRs stay on HOLD.** This report approves nothing. Browser, provider and owner gates are separate.

I read all 733 packet lines and all 9 entries.

## Inspected ranges

- **Read in full:** current `tools/migrations/cli-paths.json:1-31`, `manual-symbols.json:1-123`, `module-paths.json:1-297`.
- **Partial reads:** `migrate_module_paths.py:18-101`, `:100-180`, `:685-700`.
- **Pattern checks:** `symbol-paths.json` for keys involving servers, `AppServer`, `opencode`, `sanitized`, `feedback` and `workflow`; the classes in `agents/agents/codex/controller/service.py`; `tests/test_shared/test_migration` for `runtime.servers`, `AppServer`, `agents.feedback` and `agents.workflow`; whether `integrations/langflow/feedback/__init__.py` exists.

## Dispositions (versions grouped by path)

| Old PR / path | Original change | Disposition | Current evidence |
|---|---|---|---|
| 213/214/216 `cli-paths.json` (3 versions) | 213 retargeted `runtime.servers` to `codex.native.server`; 214 removed it (servers are not CLIs); 216 retargeted the Agent CLIs to `agents.agents.*.cli` | **PRESERVED** | No servers entry. `:2-4`, `:6`, `:20` hold the PR216 targets. The migration README says servers belong in the module map (`:28-29`). The later move of the GitHub/Skills CLIs to `interface` (`:8-13`, `:23-30`) is consistent. |
| 213/214 `symbol-paths.json` (2 versions) | 213: `AppServer`→`native.server`, `SplitAppServer`→`split.server`, retired-helper keys removed. 214: those server keys removed again; OpenCode `SECRET_KEYS`/`sanitized` → `activity.redaction.*`; native OpenCode helpers removed | **Mostly superseded by manual refusals** | The retired helpers are now refusals in `manual-symbols.json`: `_docker_*` (`:70-71`, `:89-90`, `:105-106`), `docker_environment`/`run_docker`/`cli_environment`/`command` (`:74-78`, `:95-99`), `_advertised_models` (`:69`, `:88`, `:104`) and OpenCode `normalize_message`/`turn_parts`/`OpenCodeHTTP`/`_remove_owned`/`worker_command` (`:81-85`, `:110-111`, `:119-121`). `opencode_activity.sanitized` now maps to `agents.activity.redaction.utils.sanitized` (`symbol-paths.json:65`, `:1262`). Exception: `runtime.servers.AppServer` is auto-mapped again. → D1 |
| 213/214/216 `module-paths.json` (3 versions) | 213/214: added then removed `runtime.servers`; 214 removed the `opencode.constants`/`opencode_events` modules; 216 made the large move to `agents.activity`, `agents.agents.*`, `agents.interface`, `orchestration`, `work_graph.runs`, `git.credentials.helper` and similar | **PRESERVED**, with two gaps | Every one of the ~150 PR216 targets I compared is present at the same or a later owner (e.g. `:2-48`, `:55-134`, `:140-148`, `:181-194`, `:231-249`, `:295`). The OpenCode modules are now refusals (`manual-symbols.json:55`, `:59`, `:112`). Missing entries → D2. Reintroduced servers entry → D1. |
| 216 `manual-symbols.json` (added) | 35 refusals for the retired Git helpers | **PRESERVED**, with stronger messages and wider coverage | All 35 keys are present (`:2-29`, `:66`, `:72`, `:91-94`, `:101`, `:107`). It adds `VerifiedGitStage.git` (`:21`) and the private `SkillSources` methods (`:30-54`). The check runs before any rewrite: a regex over the whole source plus import and attribute AST checks (`migrate_module_paths.py:109-163`, `:178`). |

## Findings

**nonpython-migration-metadata-1-D1: a retired Codex server alias is automatically renamed again, against the manual-only policy**
- **Applies to:** implementation (offline migration tool).
- **The current mappings:**
  - `module-paths.json:119` maps `laomedo.agents.runtime.servers` → `agents.agents.codex.controller.service`;
  - `symbol-paths.json:441` maps `runtime.servers.AppServer` → `…controller.service.CodexController`. That module defines only `CodexController` (`service.py:18`).
- **The policy they contradict:**
  - `manual-symbols.json:67-68` and `:102-103` say the same class under its other aliases needs manual migration: "constructor/protocol changed … an import rename is insufficient";
  - `:80` says the equivalent `providers.codex.servers` module has "no safe automatic module mapping";
  - `:87` makes `runtime.servers.SplitAppServer` manual. `runtime.servers.AppServer` is missing from the manual list.
- **History:** PR214 deliberately removed both automatic entries, and the final tree brings them back.
- **Effect:** `from laomedo.agents.runtime.servers import AppServer` is silently rewritten to a class with a different constructor.
- **Coverage:** `tests/test_shared/test_migration` has no test for `runtime.servers` or `AppServer`.
- **Uncertainty:** I didn't read the aliasing logic in the symbol rewrite (`:300-352`). The mismatch between the maps is certain.

**nonpython-migration-metadata-1-D2: PR216's package-level module mappings were dropped**
- **Applies to:** implementation.
- **The dropped entries:** `laomedo.agents.feedback` → `integrations.langflow.feedback` (old diff `:563`) and `laomedo.agents.workflow` → `work_graph.runs` (`:626`). Only their submodules survive (`module-paths.json:60`, `:123-126`).
- **Effect:**
  - the matcher needs an exact key (`:41-45`, `:306`), so a bare `import laomedo.agents.feedback` is not rewritten;
  - the retired-reference guard (`:77-89`, `:686-692`) refuses only *children* of mapped keys, so the stale import is also not refused. The output silently keeps an unresolvable import.
- **Target exists:** `integrations/langflow/feedback/__init__.py`.
- **Uncertainty:** a later commit outside these inputs may have dropped them on purpose. I found no record of that.

**nonpython-migration-metadata-1-Q1: inconsistent handling of the retired OpenCode `sanitized`**
- **Applies to:** implementation.
- **Detail:** `opencode_activity.sanitized` is still automatic (`symbol-paths.json:65`). `opencode_events.sanitized` is manual (`manual-symbols.json:65`, `:118`). Both pointed at the same function in PR214. This may be deliberate (only the events parser was retired). It should be confirmed, because the policy differs per alias.

**nonpython-migration-metadata-1-S1: map consistency is not tested**
- **Applies to:** implementation and tests.
- **Detail:** I found no test asserting that a symbol with a manual refusal under one alias has no automatic mapping under another. A table-driven check over the symbol, manual and module maps would have caught D1.

## Leftovers / UNVERIFIED

- I compared only the symbol-paths keys relevant to the hunks. I didn't diff the remaining ~1,200 entries.
- I didn't trace the alias-rewrite branch at `migrate_module_paths.py:300-352`.
- I checked only `test_shared/test_migration` for coverage, not other test folders.