# nonpython-examples-history-2: conservation report (read-only)

**All 23 PRs stay on HOLD.** This report approves nothing. Browser, provider and owner gates are separate.

I accounted for all 44 entries (lines 1-1752). Every graph-JSON entry is a refresh of the embedded component code plus its `code_hash`. I read those by their changed module paths and hash pairs, not as full embedded source. The Markdown entries (`:382-419`, `:1099-1129`, `:1342-1356`) I read in full.

## What each PR changed

| PR | Embedded-import or doc change |
|---|---|
| 216 | Same moves as history-1: `agents.feedback.pr`/`agents.contracts.output`/`codex_agent` to their new owners. Also regenerated the built-in Chat Input/Output nodes (`45974e6b1909→e132528833f9`, `84009527d08c→dca617672262`) and added `experiments/GIT-API-MIGRATION.md`. |
| 221 | Component code refresh only, with no import moves. |
| 224 | `skills.{sources,operations}.client` → `skills.interface.*.client`; `github.pull_requests.client` → `github.interface.pull_requests.client`; the README CLI paths moved to `interface.*.cli`. |
| 231 | `github.issues.contract` → `github.contract`; `github.issues.utils` → `github.issues.context_reader`. |
| 238 | Refreshed stale embedded PR/Skill components (the PR node gains the `integrations.langflow.feedback.pr` import). |

## Dispositions (duplicate paths grouped)

| Old PR / path group | Disposition | Current evidence |
|---|---|---|
| 216/221/224/231 `langflow-workgraph-demo/flow.json` (4 versions) | **PRESERVED**, at a later state | `:30` `github.issues.context_reader`; `:181` `skills.interface.*.client` and `integrations.langflow.feedback.pr`; `:543` `agents.interface.output.utils`. `444ef09ded09` is the PR231 head. Guarded by `component-templates.json:75` and `test_legacy_contract_migration.py:19`. |
| 221/224/231 `langflow-contract-routing/flow.json` (3 versions) | **PRESERVED** | The same canonical imports (checked in history-1). Hashes `444ef09ded09`, `3022cec0907e`, `e37a0e54002c`, `ee6d6e77fad8` match the PR224/231 heads. |
| 216/221 `skill-agent-pilot/pilot-flow.json` (2 versions) | **Partly preserved** | The PR221 runner node survives (`:459` `8e37d0d77c67`, bound by `test_pilot_flow.py:22-25`). The PR216 built-in regeneration is not present (`:40` `45974e6b1909`, `:504` `84009527d08c`). → Q1 |
| 216/221/224/231/238 `github-pr/{flow,four-node-flow,original-agent/flow}.json` (12 versions) | **INTENTIONALLY_SUPERSEDED** | Replaced by the builder in `examples/github/build_flow.py` (README `:28`, `:79`). The old graphs are on exp at `714db418` `archives/github-244` (README `:100-104`). |
| 216/221/224/238 `skill-operations/{flow,overview-flow}.json` and `skill-summary/flow.json` (10 versions) | **INTENTIONALLY_SUPERSEDED** | Replaced by `examples/skills/build_flow.py` (README `:23-27`). The originals are on exp at `1d3c2aa2` (`:47-48`). |
| 216/221/224 `claude-agent/flow.json` and `current-template-flow.json` (4 versions) | **INTENTIONALLY_SUPERSEDED** | Replaced by `examples/agents/build_flow.py`. The PR221 template survives as an exact blob, `tests/test_agents/test_examples/data/claude-template.json`, with its digest pinned at `component-templates.json:5-13`. |
| 216/221/224 `native-codex-node`, `opencode-agent` and `opencode-node` `flow.json` (6 versions) | **INTENTIONALLY_SUPERSEDED** | Replaced by the agents builder plus the wire inputs `test_examples/data/{codex,opencode}.json` (`component-templates.json:32-61`). |
| 221 `agent-handoffs/flow.json` | **INTENTIONALLY_SUPERSEDED** | Replaced by `test_examples/handoffs.py` (already settled in history-1). |
| 224 `github-issue/README.md` and `github-pr/README.md` (CLI moves) | **PRESERVED**, relocated | `docs/features/github/connection.md:31` (`interface.issues.cli`) and `:42` (`interface.pull_requests.cli`). |
| 224 `skill-operations/README.md` (CLI move) | **PRESERVED**, relocated | `docs/features/skills/walkthrough.md:88` (`interface.operations.cli`). |
| 216 `experiments/GIT-API-MIGRATION.md` (added) | **GAP** in the docs | The file is absent from 1eb10a1f, and nothing references it. → D1 |

## Findings

**nonpython-examples-history-2-D1: the Git API constraint note for historical experiments was dropped**
- **Applies to:** spec/docs and experiments on exp.
- **What it said:** PR216's note listed 13 historical experiments that depend on removed private Git helpers. It said they stop at the first retired helper call, that they are not launcher examples or acceptance proof, and how to migrate them before rerunning.
- **What's on develop now:** those experiments are still there and still import the retired helpers. For example:
  - `exp104/live_probe.py:28-30` imports `github.transport.git.utils._base_git_environment`, `_credential_environment` and `_push_failure_category`;
  - `exp93/real_stage_probe.py:34,36` imports `_base_git_environment` and `_NoRedirect`;
  - `real_stage_probe.py:38-39` and `s11_probe.py:30-31` import `agents.providers.codex.*`.
- **Partial replacement:** `tools/migrations/README.md:34-43` covers only the inventoried internal-probe controls, not this list.
- **Uncertainty:** PR216's explicit refusal helper is Python and belongs to the Python packets, so I haven't verified it here. If it is also gone, these probes fail with an ImportError rather than a documented refusal.

**nonpython-examples-history-2-Q1: built-in node refresh applied unevenly; the pilot is not a consolidated example**
- **Applies to:** implementation data and examples.
- **Uneven hashes:** the pilot flow and `test_examples/data/codex.json:40,1204,1483` keep the pre-PR216 Chat Input/Output hashes. `controller.json:39,798,1077` has the PR216-regenerated ones.
- **No guard either way:** `component-templates.json` checks only custom Laomedo nodes. The pilot's digest (`:72`) freezes whichever built-in state is current, so I can't tell from guards which state is correct for the pinned Langflow.
- **Not in the index:** `examples/skill-agent-pilot/` is not listed in `examples/README.md:5-7`.
- **Broken commands:** its README still launches retired modules — `agents.providers.codex.cli` (`:42`, `:53`) and `laomedo.activity.rollout_export` (`:81`), which now exists only under `agents/agents/codex/activity/`. This extends documentation-1 D2 to the examples.

**nonpython-examples-history-2-S1: example READMEs no longer show service start commands**
- **Applies to:** docs.
- **Detail:** the consolidated `examples/github/README.md` and `examples/skills/README.md` link to setup docs instead of showing the `interface.*.cli` start commands that PR224 corrected. The commands are correct where they now live. An inline pointer would help discoverability. Optional.

## Inspected ranges (final worktree)

- **Read in full:** `examples/github/README.md:1-105`, `examples/skills/README.md:1-51`, `tests/test_pilot_flow.py:1-34`.
- **Partial reads:** `component-templates.json:1-80`.
- **Pattern checks:**
  - module/hash patterns across the three surviving graphs and `test_examples/data/*.json`;
  - `python -m laomedo.*cli` across `docs/` and `examples/*.md`;
  - the imports in the four listed experiment probes;
  - a search for `GIT-API-MIGRATION` (none found).

## Leftovers / UNVERIFIED

- The archive contents on exp at `714db418` and `1d3c2aa2`.
- Whether the three builders reproduce the old graphs' ports and pins.
- PR216's experiment refusal helper (Python).
- Which built-in component hash matches the pinned LFX version (Q1).