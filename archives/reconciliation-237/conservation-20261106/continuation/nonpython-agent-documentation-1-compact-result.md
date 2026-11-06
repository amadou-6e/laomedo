# nonpython-agent-documentation-1: conservation report (read-only)

**All 23 PRs stay on HOLD.** This report approves nothing. Browser, provider and owner gates are separate.

The biggest problem is that five Agent feature docs in the final tree are still at their pre-PR214 text. Two of them now contradict the shipped code.

I accounted for all 38 entries (lines 1-1833).
- **Read in full:** `:73-106`, `:239-475`, `:924-1073`.
- **Exact blobs:** 17 entries (16 in the grouped row below, plus `docs/architecture/agent-communication.md`). I reused the hash match and checked the code each one documents exists.
- **Not compared line by line:** the remaining added READMEs. I pattern-checked them only.

## Inspected ranges (final worktree)

- **Read in full:** `docs/features/agents/runner/docker-sandbox.md:1-27`, `mediation/host-services.md:1-30`, `src/laomedo/agents/README.md:1-67`.
- **Pattern checks:**
  - `docs/features/agents/README.md` and `local-service.md`;
  - `architecture.md:20-21`;
  - links to `codex/connection.md` repo-wide;
  - the `**/http/*.py` modules under `agents`;
  - retired paths across `src/laomedo/agents/**/*.md`;
  - `claude/settings.py:5`, `host/runner/service.py:55-63`, `opencode/history/settings.py:35`, `test_boundaries.py:35`.
- **Cross-check:** the same doc strings against the Agent250 head.

## Dispositions

| Old PR / path | Disposition | Evidence |
|---|---|---|
| 214 `docs/features/agents/runner/local-service.md` | **GAP** | Current blob `2fb486ea` is the PR214 *base*. → D1 |
| 214/216 `runner/docker-sandbox.md` (2 versions) | **GAP** | Current `e9564ce6` is the PR214 base: "legacy Codex runner" (`:3`), the split policy "unchanged" (`:10`), and the seccomp link to the retired `agents/providers/...` path (`:9`). → D2 |
| 214 `providers/opencode/activity.md` | **GAP** | Current `0ce5eb1b` is the PR214 base. The ACP child-capture, export-deadline, real-run evidence and 210 s/240 s node-wait sections are absent. The code still has `LAOMEDO_OPENCODE_HISTORY_EXPORT_SECONDS` (`history/settings.py:35`). → D3 |
| 214 `mediation/host-services.md` | **GAP** | The incomplete-mediation warning for #215 (old diff `:264-273`) is absent; the current file starts at the old `:1-7`. → D4 |
| 214 `docs/features/agents/README.md` (provider link) and 214 `providers/codex/connection.md` (exact) | **GAP** in the link; the page itself is PRESERVED | The page exists, but nothing links to it: the current README lists only OpenCode and Codex parity (`:26-29`), and no repo-wide link was found. → D5 |
| 216 `docs/features/agents/architecture.md` | **GAP** | `:20-21` still name `agents/runtime/runner.py` and `agents/providers/{…}`, which are retired (`src/laomedo/agents/providers` is absent). → D2 |
| 214 `docker/codex-git/README.md` (deleted) | **PRESERVED** retirement | No references remain. `test_boundaries.py:35` asserts `docker/codex-git/Dockerfile` is absent. |
| 214/216 `src/laomedo/agents/README.md` (2 versions) | **INTENTIONALLY_SUPERSEDED** | Rewritten declaratively (`:1-67`) with the PR216 objects (`BaseAgent`, `*Agent`, `HttpAgentBridge`, `AgentHandoffController`, `ActivityCapture`, `AgentWorkspace`) and the work_graph/git/github ownership. PR216's migration-checkpoint chronology was dropped; that is consistent with the declarative-README rule. `:57-61` keeps the specs #403 / ACP #214 evidence dependency. |
| 216 added READMEs: `activity/`, `agents/agents/`, `base/`, `claude/`, `claude/activity`, `claude/auth`, `codex/`, `opencode/`, `opencode/activity`, `artifacts/`, `interface/` (11, current blob differs) | **PRESERVED**, rewritten (not compared line by line) | All exist. A search of `src/laomedo/agents/**/*.md` found no references to `agents/providers`, `agents/runtime`, `activity/agent_activity`, `host/credentials/{claude,opencode}` or "PROPOSED". |
| 214 exact `docker/codex-acp/README.md`; 216 exact `activity/acp`, `activity/runner`, `activity/runner/http`, `base/acp`, `claude/activity/http`, `claude/http`, `codex/activity`, `codex/controller`, `codex/resources/codex-seccomp.md`, `codex/split`, `opencode/auth`, `opencode/history`, `opencode/http`, `interface/langflow` (16) | **PRESERVED** | Unchanged bytes. The http leaves have `handler.py`/`server.py` (`activity/runner/http`, `claude/http`, `claude/activity/http`, `opencode/http`). The seccomp resource binding is settled (`codex/settings.py:46-51`). The codex-acp README's provenance mixing stays as runtime-build Q1. |

## Findings

**D1: `local-service.md` contradicts the runner's configuration**
- **Applies to:** spec/docs.
- **Detail:** the example image `laomedo-claude-controller:2.1.310` (`:23`) is out of date: the code pins `…:2.1.310-acp0.98.0` (`claude/settings.py:5`).
- **Detail:** `:43` tells Codex users to omit `lease_service`. `host/runner/service.py:55-56` makes it required for every provider and defaults it to `lease` beside the state directory, which is what PR214 documented.

**D2: retired paths in active Agent docs**
- **Applies to:** spec/docs.
- **Locations:** `docker-sandbox.md:9` (broken provenance link), `docker-sandbox.md:3`, `:10`, `:20-21` (legacy runner, and the split executor's checksum-verified seccomp requirement removed), and `architecture.md:20-21`.
- **Pattern:** this matches the open documentation-1 D2.

**D3: OpenCode ACP capture contract and evidence lost**
- **Applies to:** spec/docs and visual evidence.
- **What's missing:**
  - live root stream versus post-export child activity;
  - the 120 s/30 s budgets and the configurable 45-600 s variable;
  - the "timeout ≠ zero usage" rule;
  - the 210 s default / 240 s maximum node wait and its unconfirmed-outcome rule;
  - the owner-authorized real child-capture evidence (`f303cdb`, 5,363 tokens) and its limits.
- **Uncertainty:** the code still has the env variable, but I didn't verify the 120/30/210/240 values in code.

**D4: incomplete-mediation warning lost.** Applies to spec/docs. `host-services.md` again reads as working setup. The current file does not record that native-command mediation failed in the real check at `4eb5d95` (`mediation request failed`), the link to issue #215, or that the `exp139` mailbox relay is only a proposal.

**D5: the Codex ChatGPT connection guide is orphaned.** Applies to docs. `docs/features/agents/providers/codex/connection.md` is preserved, but nothing links to it. PR214 added the link in the Agents README (old diff `:249-250`).

**Q1: all five pre-PR214 feature docs came from the Agent replacement, not from a later merge.**
- **Applies to:** spec/docs.
- **Detail:** Agent250 also lacks these strings; only `connection.md` matched there. So D1-D5 belong to the Agent replacement branch itself.
- **Uncertainty:** whether the owner meant to defer feature docs from that branch.

## Leftovers / UNVERIFIED

- Line-by-line comparison of the 11 rewritten PR216 leaf READMEs (`:1073-1833`, minus the exact blobs).
- `agent-communication.md` (exact) incoming links.
- The OpenCode budget values in code (D3).