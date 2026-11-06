# nonpython-migration-metadata-2: conservation report (read-only)

**All 23 PRs stay on HOLD.** This report approves nothing. Browser, provider and owner gates are separate.

I accounted for all 6 entries (lines 1-1795).
- **Read in full:** the PR221/222/223 entries (`:1508-1795`), PR216's first replacement block and its hunks at `:879-1018`.
- **Sampled, not read:** the rest of PR216's symbol-map rewrite (`:7-1507`, about 708 additions and 532 removals). I checked it by target-namespace patterns and 25 spot checks of the current values, not line by line.

## Inspected ranges

- **Current files read:**
  - `tools/migrations/retained-shared-callers.json:1-60`;
  - `tests/test_shared/test_formatting/test_policy.py:1-85`;
  - `pyproject.toml:28-41`;
  - `tests/test_shared/test_migration/test_shared.py:14-158`;
  - `tests/test_shared/test_migration/test_paths.py:195-262`.
- **Pattern checks:**
  - `symbol-paths.json`: all `NoRedirect` keys, retired target namespaces, and the 25 sampled keys;
  - the `class` definitions of `GitCommandTimeout`, `HttpAgentBridge` and `AgentHandoffController`;
  - every consumer of `historical-sources.json`.

## Dispositions

| Old PR / path | Original change | Disposition | Current evidence |
|---|---|---|---|
| 216 `symbol-paths.json` | Retargets every published symbol to the PR216 owners: `agents.activity`, `agents.agents.*`, `agents.interface`/`bridge`, `orchestration`, `git.settings`/`errors`, `git.credentials.helper`, `work_graph.runs`, `agents.agents.*.auth`. Renames classes (`RunnerCapture→ActivityCapture`, `*Runner→*Agent`, `Runner→BaseAgent`, `GitTreeTimeout→GitCommandTimeout`, `RunnerAdapter→HttpAgentBridge`, `BoundedController→AgentHandoffController`). Removes the retired Git helper keys. | **PRESERVED**, with later moves | All 25 sampled keys are present with PR216's targets or later ones (e.g. `:2`, `:5`, `:120-128`, `:136`, `:200`, `:366-372`, `:440`, `:637`, `:725-728`, `:757`, `:845-853`, `:1146-1194`, `:1279`). No current target is in a retired namespace (empty search over `skills.registry.utils`, `skills.workspace.`, `agents.providers`, `agents.runtime`, `agents.contracts`, `activity.` and others). The removed Git helpers are refusals in `manual-symbols.json` (metadata-1). The `opencode_events.*` mappings PR216 kept automatic are now manual refusals (settled ACP retirement). |
| 216 `symbol-paths.json` (guards) | — | **Adequate assertions** | `test_shared.py:18-37` checks targets have current owners and that the symbol and manual maps share no key. `:39-83` checks each target is declared and no key is shadowed by a manual *prefix*. `:102-155` resolves the Skills/Git/HTTP targets. `test_paths.py:207-244` executes rewrites of migrated multi-generation imports. |
| 221 `tools/formatting/historical-sources.json` (exact blob) | Seven sealed experiment sources, with SHA-256 and the evidence files that contain it | **PRESERVED**, with checked consumers | Unchanged bytes. `test_policy.py:56-75` checks each hash, its presence in the evidence and Black's force-exclude. `pyproject.toml:32-38` lists exactly these seven paths. Documented at `docs/architecture/python-formatting.md:53`. |
| 222 `module-paths.json` | `skills.sources.transport` → `http.redirect` | **PRESERVED** | `module-paths.json:285`. |
| 222 `symbol-paths.json` | 15 `NoRedirect`/`_NoRedirect` aliases → `http.redirect.NoRedirect`, plus 2 new keys | **PRESERVED** | All 17 present (`:647`, `:691`, `:743`, `:752`, `:765`, `:804`, `:835`, `:1097`, `:1106`, `:1140`, `:1381`, `:1403`, `:1527`, `:1549`, `:1603`). The SIWC/OpenCode credential handlers keep their own classes (`:859-877`, `:1264`, `:1356`), as `http/README.md` requires. |
| 222 `retained-http-callers.json` (added) | Inventory of the four probes behind the `_NoRedirect` alias, with notes on their provenance | **INTENTIONALLY_SUPERSEDED** (settled alias retirement) | All four probes are in `retained-shared-callers.json` (`:7`, `:35`, `:51`, `:153`), with post-format hashes and explicit policy (`:3`). The per-file provenance notes were not carried over. → Q2 |
| 223 `module-paths.json` | `bundle_ingest` and `skills.ingestion.*` → `host.publication.ingestion.*` | **PRESERVED** | `module-paths.json:136`, `:260-265`. |

## Findings

**nonpython-migration-metadata-2-Q1: automatic class renames have no constructor-compatibility check**
- **Applies to:** implementation.
- **What happens:** PR216 auto-maps renamed classes, and the final tree keeps this:
  - `handoff_http.RunnerAdapter` → `HttpAgentBridge` (`symbol-paths.json:845`);
  - `handoffs.BoundedController` → `AgentHandoffController` (`:846`);
  - `GitTreeTimeout` → `GitCommandTimeout` (`:728`, `:757`);
  - `*Runner` → `*Agent` (`:128`, `:200`, `:440`). `test_paths.py:243` confirms this is done as an `as LocalRunner` alias.
- **Why it matters:** the same maps treat the `AppServer` → `CodexController` change as manual-only because "an import rename is insufficient" (`manual-symbols.json:67`).
- **What the tests cover:** the resolution tests (`test_shared.py:39-83`) prove these targets exist, not that their signatures match. `test_paths.py:246-261` covers changed interfaces only for leases, activity and work_graph.
- **Uncertainty:** I didn't compare the old and new constructors. These may well be compatible renames.

**nonpython-migration-metadata-2-Q2: provenance uncertainty for the retained probes no longer recorded**
- **Applies to:** history and spec/docs.
- **What was lost:** PR222 recorded that the `exp100` LIVE-MANIFEST pin does not match the current file, that `exp104_managed` is an UNEXECUTED candidate, and that the other probes have no established seal match (old diff `:1598-1601`). `retained-shared-callers.json:3` keeps only a general "no historical acceptance claim".
- **Why it matters:** the hashes there (e.g. `:8` `20175fe7…` vs PR222's `aae0b0c5…`) are post-format bytes, so that uncertainty matters more now. The document that also described it (`node-http-boundaries.md`) has been retired (documentation-1 Q1).

**Correction to metadata-1 S1 and the coverage note under D1:**
- **What's already tested:** `test_shared.py:21` asserts the symbol and manual maps share no key, and `:39-48` asserts no symbol key sits under a manual prefix. Those checks already exist.
- **What's still uncovered:** they don't recognise that `agents.runtime.servers.AppServer` and `agents.local_runner.AppServer` are the same class. So metadata-1 D1 stands unchanged.
- **S1 narrows** to "add equivalence across aliases of the same class to the existing consistency test".

## Leftovers / UNVERIFIED

- The rest of PR216's ~1,240 changed symbol lines beyond the 25 spot checks and the namespace patterns. The resolution tests give broad structural coverage, but I didn't run them.
- Whether the constructors of the renamed classes match (Q1).
- Whether the provenance notes moved to an exp archive (Q2).