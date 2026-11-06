# nonpython-examples-history-1: conservation report (read-only)

**All 23 PRs stay on HOLD.** This report approves nothing. Browser, provider and owner gates are separate.

I accounted for all 12 entries in the packet (lines 1-1811). The graph-JSON lines embed whole component sources, so I read those hunks by their changed module paths and `code_hash` values, not as full text. The 1300-line added copy at `:470-1769` was checked by its module paths and node hashes only.

## Inspected ranges (final worktree 1eb10a1f)

- **Read:** `tools/migrations/README.md:1-54`, `protected-graphs.json:1-10`, `agent-history.json:1-12`, `migrate_module_paths.py:870-909`, `test_shared/test_migration/README.md:1-25`, `test_revisions.py:100-144`, `examples/README.md:1-12`, `tests/test_agents/test_examples/README.md:1-23`.
- **Single-line or pattern checks:** imports in `experiments/feasibility/107/README.md` and its two probes; the module paths in `langflow-contract-routing/flow.json`; the consumers of the contract-routing flow and `test_examples/handoffs.py`.

## What PR213/216 changed

- **PR213:** rewrote the run instructions for two retired CLI-only probes in feasibility experiment 107 as historical notes, and added a retirement paragraph.
- **PR216:** moved the imports in the embedded components of nine example graphs to their new owners. For example:
  - `agents.contracts.*` → `agents.interface.output.utils` / `integrations.langflow.output.utils`;
  - `activity.agent_activity` → `agents.activity.utils`;
  - `agents.handoffs.*` → `agents.orchestration.controller` / `agents.interface.bridge`;
  - `providers.claude.catalog` → `agents.agents.claude.catalog`;
  - `agents.feedback.pr` → `integrations.langflow.feedback.pr`.

  It refreshed each `code_hash` to match. It also added a manifest of immutable historical exports (`agent-module-history.json` and `.md`) and an exact baseline copy of one historical graph.

## Dispositions

| Old PR / path | Disposition | Current evidence |
|---|---|---|
| 213 `experiments/feasibility/107/README.md` | **GAP** | The current blob `e712f3bf` is the PR213 *base*, so all of PR213's changes are lost. → D1 |
| 216 `agent-handoffs/flow.json` and `loop-flow.json` (grouped: same import moves and hash refresh) | **INTENTIONALLY_SUPERSEDED** | The files are gone. Handoff and controller graphs are now built by `tests/test_agents/test_examples/handoffs.py:22,85`. Historical copies are on exp at `f6112286` (README `:17-18`). |
| 216 `claude-agent/current-template-flow.json` and `flow.json` (grouped) | **INTENTIONALLY_SUPERSEDED** | Replaced by the builder in `examples/agents/build_flow.py`, listed in `examples/README.md:7`. The copied wire inputs in `test_examples/data/*.json` have canonical imports (README `:20-23`). |
| 216 `github-pr/flow.json`, `four-node-flow.json` and `original-agent/flow.json` (grouped) | **INTENTIONALLY_SUPERSEDED** | Replaced by `examples/github/build_flow.py`, listed in `examples/README.md:6`. |
| 216 `original-agent/historical-flow-before-agent-module-refactor.json` (added) | **Moved to exp** | It is listed as immutable at `protected-graphs.json:6`. Its bytes on exp are UNVERIFIED. |
| 216 `examples/agent-module-history.json` (exact blob → `tools/migrations/agent-history.json`) | **PRESERVED as bytes; consumer superseded** | The path refusal now reads `protected-graphs.json` (`migrate_module_paths.py:882-892`). That list has the same seven paths. The refusal is tested at `test_revisions.py:125-138`. No code reads `agent-history.json`. → D2 |
| 216 `examples/agent-module-history.md` (added) | **INTENTIONALLY_SUPERSEDED** | Its content is condensed into `tools/migrations/README.md:12,45-53` and `test_examples/README.md:20-23`. The regeneration-versus-migration hash rule survives at `migration/README.md:51-53`. |
| 216 `langflow-contract-routing/flow.json` | **PRESERVED**, with later import moves | The current file imports `skills.interface.{sources,operations}.client` (`:181`), `integrations.langflow.feedback.pr` (`:181`) and `agents.interface.output.utils` with `integrations.langflow.output.utils` (`:1083`). Consumers: `tests/contracts/component-templates.json:131` and `test_integrated_contract.py:11`. |

## Findings

**nonpython-examples-history-1-D1: retirement notes for feasibility experiment 107 lost; the probes stay on develop and cannot run**
- **Applies to:** spec/docs and experiments on exp.
- **What changed:** the README still says "Run the probe from the Laomedo checkout" (`README.md:22`, `:85`) and gives commands at `:26` and `:89-94`. PR213's three historical-invocation edits and its retirement paragraph (old diff `:11-14`, `:22-25`, `:33-34`) are all absent.
- **Why it matters:** both probes are still on develop and import the retired `laomedo.agents.providers.codex.*` package:
  - `probe_controller_env.py:14-16`;
  - `probe_remote_executor.py:23-28`.
- **Rule conflict:** this also goes against the rule that experiments live on exp.
- **Uncertainty:** low.

**nonpython-examples-history-1-D2: `agent-history.json` is orphaned data that the docs say is consumed**
- **Applies to:** implementation data and docs.
- **The claims:** `tests/test_shared/test_migration/README.md:9-10` says "the offline CLI consumes it", and `tools/migrations/README.md:12` says the same in substance.
- **What the code does:** the only consumer is the CLI's read of `protected-graphs.json` (`migrate_module_paths.py:884`).
- **What's left:** all seven `current_template` entries (e.g. `:5`) point at removed paths under `examples/claude-agent`, `github-pr`, `skill-*` and similar. Its SHA-256 and Git-blob provenance is never checked.
- **Fix:** either retire the file or wire it in as the provenance check, and correct both READMEs.
- **Uncertainty:** I did not check whether PR216's own CLI verified those hashes. Its README only claimed the refusal.

**nonpython-examples-history-1-Q1: historical exports moved to exp are not verified in this audit**
- **Applies to:** history preservation.
- **Detail:** develop points to exp at `f6112286` (`test_examples/README.md:18`) for the seven protected originals and the historical copy added by PR216. I did not read that checkout, so I can't confirm the exact bytes.

**nonpython-examples-history-1-S1: the refusal test covers only one protected path**
- **Applies to:** implementation and tests.
- **Detail:** `test_revisions.py:126` exercises only `executed-flow.json`. A table-driven loop over `protected-graphs.json` would keep all seven protected.

## Leftovers / UNVERIFIED

- Exact bytes on exp at `f6112286` (Q1).
- That the builders in `examples/agents` and `examples/github` reproduce the ports and Skill pins of the old graphs. I did not read the builders.
- What `component-templates.json` asserts beyond the contract-routing path entry at `:131`.