# Final unread-hunk coverage and integration ledger

The four gaps you listed are closed: I found no defects in the remaining JSON, migration-map and Activity hunks, and CAT-Q1 is confirmed from the actual route. The code, tests, visuals and docs all have scoped approvals. The integration verdict is still **INCOMPLETE**, because live acceptance, the canonical spec, the owner's graph validation and CI on 341c68f3 are outside what a code review can supply. This is not merge or issue-closure authorization.

I re-read `AGENTS.md` lines 80-139 in full this turn; lines 1-79 come from an earlier read in this session.

## 1. JSON fixtures (all 3 files in the field audit)

**`projector-records.json`**
- Records 4 to 7 are OpenCode records. Only their cost metadata changes:
  - `source_record` becomes the OpenCode runtime catalog record (`/provider`, runtime 1.18.33);
  - `catalog_date` becomes null;
  - `basis` becomes the OpenCode basis text.
- This matches `estimate_native` exactly.
- No `amount`, usage, turn, thread or item value changes. So the old fixture had Codex price metadata attached to OpenCode results, and the amounts were already the OpenCode ones.
- Records 2 and 3 are Claude records. Their reason, basis and `catalog_date` now match Claude's `estimate`, which always returns an unknown amount. Before, they said "no verified price entry" from the Codex table.
- No amount went from unknown to known.

**`claude-template.json` and `claude.json`**
- The embedded component source changes by exactly one line: `EFFORTS` is imported from `claude/settings` instead of `claude/catalog`. That matches `components/laomedo/claude_agent.py` in the remainder diff.
- `code_hash` changes from b4742f59e64a to 6c307b7e4f61.
- No graph, edge, template or position field changed, so no topology change is hidden behind the hash refresh.
- I did not recompute the new hash myself. I'm relying on the current source/hash contract test passing.

## 2. Migration-map remainder

I checked all 53 changed targets. Every one resolves to a current defining module or symbol:
- `codex/activity/cost.estimate` and `codex/activity/settings` CATALOG_DATE/RATES/SOURCES;
- `activity.timeline.KEYS`;
- `codex/activity/projection._parent`;
- `activity.utils.normalize_telemetry`;
- `base.settings.ROLE_INIT_LOCK`;
- `claude.settings.EFFORTS`;
- `claude.policy.ClaudeRuntimePolicy` and `claude.executor.ClaudeCommandExecutor`;
- `opencode.executor.OpenCodeCommandExecutor` and `opencode.runtime.OpenCodeAgentRuntime`;
- `codex.runtime.CodexAgentRuntime` and `codex.split.executor.CodexCommandExecutor`.

None of them points to a retired ABC or projector.

**Info:** these maps move import paths, not APIs. Code that called `CommandService.mediate`, or `CommandBroker.token` and `.server`, must now go through `.transport` or `.broker`. That's expected for import-migration tooling and is not a defect.

## 3. Activity hunks not read before

- The old shared `project` body (`roles-activity-unread-hunks.diff:16-305`) is the same code as the current `timeline.py`, line for line. The only changes are four injected policies:
  - `_parent` becomes `parent_of`;
  - `_telemetry` becomes `normalize_telemetry`;
  - the hard-coded `claude/result` check becomes `is_diagnostic`;
  - the Codex `estimate` becomes a parameter.
- Kept unchanged:
  - the alias normalization;
  - the zero baseline only for a fresh thread or a newly started child;
  - backwards counters and missing cumulative totals both making usage unknown;
  - turn baselines;
  - deltas never overwriting completed items;
  - relatedness and uncorrelated counting;
  - checks against conflicting telemetry models;
  - child-pricing completeness.
- The old dispatch to OpenCode by content markers (`:1-15`) is retired; legacy rows now go through `legacy.py`.
- The `cost.py` move keeps the identical RATES, SOURCES and CATALOG_DATE.
- **Not read line by line:**
  - `:310-638`, which is the new `timeline.py` text (I read the current file in full in packet B);
  - `:639-755` and `:797` onward: utils, the Claude and Codex projection modules (current versions read in B) and the retired projector wrappers.

## 4. CAT-Q1: confirmed closed

`handler.py:37-41` serves `GET /v1/models` by calling `runner.editor_model_catalog()`, which returns the payload with only `id` and `efforts`.

## Integration ledger

| Range | Coverage | Status |
|---|---|---|
| bb250135..620ad13a (857-file base) | Archived ledger and integration result | Scoped approvals; data-fixture ranges later closed as recorded there |
| 620..089 layout | layout-cleanup, coverage-completion and roles-A visual verdicts | Code, metadata and visuals APPROVE; LC-01 fixed; LC-02 withdrawn |
| 089..a466 initial extraction | Initial verdict, then packets A, A1, A2, B, C, D, final, and this turn | All substantive hunks covered |
| Later Docker, image, catalog, interaction, Activity, runtime retirement, CI, rollout export and harness work | The separate verdict files | Each approved within its own scope |

Withdrawn design objects (`BaseAgentRuntime`, `RuntimeLaunch`, the projectors) have not returned. The retired-object guard and current source confirm this.

**Open optional items, not blocking:**
- CK-01: relative imports are not supported by the guard; no current bypass;
- IR-02: an older malformed-MCP error path.

**Scope caveat:** approval of the current runtimes is not proof of exact historical equivalence.

## What still needs reading

- **None of these is a substantive code gap:**
  - the new-file text of `timeline.py` in the historical diff (the current file was read in full);
  - the retired projector-wrapper bodies;
  - the 11 verdict reports, which I didn't re-open this turn and summarized from this session's own outputs.
- **Docs:** I did not re-read the DOC-01 and DOC-02 corrections at 341c68f3, so I'm treating them as your statement, with no recheck required.

## Remaining product and merge gates (not code gaps)

- the canonical spec (PR 403) is still a draft;
- the owner's final real-graph validation is absent;
- CI on 341c68f3 is pending;
- live coverage not run:
  - Claude restart;
  - loss of the lease supervisor;
  - physical host or daemon loss;
  - a real second daemon;
  - recovery of a terminal Activity stream;
  - the default OpenCode Console composition;
  - native GitHub mediation;
  - a live split-executor run;
- the legacy workgraph demo's obsolete Output Requirements edge stays explicitly uncovered;
- no fixture or synthetic evidence counts as native acceptance.

## Verdicts

| Area | Verdict |
|---|---|
| Implementation | **APPROVE**, within the recorded scopes |
| Tests and fixtures | **APPROVE** |
| Docs | DOC-01 and DOC-02 corrected per your report; not rechecked |
| Visual | **APPROVE**: the GUI captures and the IR-03 diagrams |
| Spec | **INCOMPLETE**: PR 403 is a draft |
| Integration | **INCOMPLETE** until the owner's graph validation, CI on 341c68f3, and the live items above |