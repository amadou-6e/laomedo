# nonpython-shared-skills-github-documentation-1: COMPLETE

I read the whole packet: the index and `.txt` lines 1-300, 301-600, 601-900, 901-1200, 1201-1500 and 1501-1825. Nothing in the packet is unread.

Current evidence is from the final combined worktree (`.tools/checkpoint-conservation-final-worktree`, 1eb10a1f), plus the earlier Agent250 `AGENTS.md` read. All 23 PRs remain **HOLD**. Nothing here is visual, and the browser, provider and owner gates are separate.

**Exact-blob entries:** I judged these by unchanged bytes plus a current owner or consumer that I checked by name:
- `git/credentials`;
- `github/workflows` (`touches_workflows` is documented in `github/README.md:36`);
- `host/runner/http` (`RunnerRequestHandler`);
- `work_graph/runs`;
- `integrations/langflow/join` (`JoinRequestHandler`);
- `native-github-mediation.md`;
- `host/credentials/siwc`, `host/mediation`, `host/publication/bundle` and `host/publication/handoff`;
- `host/publication/verified` (PR 220 version);
- `work_graph/README.md` (its models are listed at `package-layout.md:169`).

**Not checked:** that every model these READMEs name exists in `src`.

## Dispositions

| PR / path | Disposition | Current evidence |
|---|---|---|
| 213 `docs/architecture/docker-runtime-adoption.md` | **GAP** | D1 |
| 214 `AGENTS.md` (module-cohesion rules) | **GAP** | D3 |
| 221 `AGENTS.md` (Python formatting) | **PRESERVED** | `AGENTS.md:20` |
| 214 and 216 `package-layout.md` | **PRESERVED** (reworded) | **Git ownership:** `:5`.<br>**Retired procedural Git needs manual migration:** `:16`.<br>**`BaseAgent`:** `:64,199`.<br>**Canonical CLIs:** `:74-75`.<br>**Component hash refresh:** `:85-106`.<br>**`opencode_acp`:** `:209`. |
| 216 `docs/features/skills/registry.md`, `docs/getting-started.md` (CLI renames) | **GAP** | D2 |
| 216 `src/laomedo/git/README.md` | **PRESERVED** | `:12-71` covers the runner, the two environment profiles, stdin behaviour and timeout inheritance. |
| 216 `github/transport/git/README.md` | **PRESERVED**, updated | `GitHubMediatedTransport` now lives in `mediated.py` (`:6`); the runner test seam is at `:17`. |
| 216 then 220 `host/publication/verified/README.md` | **PRESERVED** (exact PR 220 blob) | — |
| 217 / 220 / 222 `github/issues` and `github/pull_requests` READMEs | **PRESERVED** | `GitHubOperationIntent` appears at `issues/README.md:20` and `pull_requests/README.md:20`. The C1 handler vocabulary moved to `github/interface/issues/README.md:11`, with the interface relocation. |
| 222 `github/README.md` | **PRESERVED**, updated | `:36` |
| 218 `skills/operations` and `skills/registry` READMEs | **PRESERVED** | `registry/README.md:45`; `operations/README.md:17,39` |
| 220 `host/leases/README.md` | **PRESERVED** | `LeaseCleanupObservation` at `:14` |
| 217 / 220 `structured-data.md`, 220 `structured-data-audit.md`, 222 `node-http-boundaries.md` | **INTENTIONALLY_SUPERSEDED** as provenance, with a residual | Q1 |
| 221 `python-formatting.md` | **PRESERVED** | Updated to the current test path (`:54`) and the historical-sources list (`:53`). |
| 221 `README.md` and `docs/architecture/README.md` formatting links | **GAP** (navigation only) | S1 |

## Findings

**nonpython-shared-skills-github-documentation-1-D1 — defect, medium. Owner: Agent docs.**
- **What happened:** the final `docker-runtime-adoption.md` is byte-identical to PR 213's *base* (blob `2da99ef0`). PR 213's rewrite was lost.
- **What the active doc says now:**
  - "not ready to merge into develop";
  - it points at retired owners such as `agents/providers/codex/runner.py`;
  - it gives the retired CLI `laomedo.agents.providers.codex.cli` (`:123`).
- **What it lacks:**
  - the runtime/Laomedo boundary statement;
  - the reconciliation procedure for receipts from older drafts;
  - documentation of `LAOMEDO_CODEX_STREAM_MAX_BYTES` and `LAOMEDO_CODEX_STREAM_STARTUP_MARGIN`. These are still read by `agents/agents/codex/controller/settings.py`, and are now documented nowhere.
- **Caveat:** PR 213's Codex `sessions.open`/`CodexLaunch` paths were superseded by ACP (PR 214). The fix should restore the still-valid parts, not the old text verbatim.

**nonpython-shared-skills-github-documentation-1-D2 — defect, medium. Owner: Agent docs.**
- **What happened:** PR 216's CLI renames were lost in two active docs. `getting-started.md`'s current blob equals PR 216's base.
  - `docs/getting-started.md:104` uses `laomedo.agents.providers.claude.cli`.
  - `docs/features/skills/registry.md:93` uses `…providers.codex.cli`.
- **Effect:** `src/laomedo/agents/providers` doesn't exist in the final tree, so both documented commands point at a module that is gone.

**nonpython-shared-skills-github-documentation-1-D3 — defect, medium. This is an instruction/spec gap.**
- **What was lost:** PR 214 added four module-cohesion rules to `AGENTS.md`:
  - import symbols directly from their defining module, with no module-prefix aliases;
  - turn large configuration literals into typed models with `to_config()`;
  - define classes at module scope, with no class factories or nested handlers;
  - apply the rules to owned or reworked code only.
- **Evidence:** the final `AGENTS.md` (the Python-cohesion section ending at `:71`) and the Agent250 copy contain none of them. The root workspace `AGENTS.md` lacks them too.
- **Partial enforcement:** some tests still enforce parts of them, e.g. the GitHub nested-class and alias guards in `test_ownership.py:17-37` and Skills' `import laomedo.` guard. But the instruction itself is gone, and it bears directly on your modularity requirement.
- **Uncertainty:** it may have been condensed on purpose.

**nonpython-shared-skills-github-documentation-1-Q1 — question. This is about docs.**
- **What's gone:** these three docs have been removed and nothing links to them:
  - `structured-data.md`
  - `structured-data-audit.md`
  - `node-http-boundaries.md`
- **What's fine:** the audit inventory and the C1 checkpoint narrative are provenance, so retiring them is acceptable.
- **What's left over:** the active conventions now exist only in scattered READMEs (`siwc`, `github`, `agents/agents/base`, `claude/activity`), not in an architecture document:
  - the `from_*`/`to_*` naming rule;
  - the distinction between reference, record and proposal;
  - `Base` only for abstract interfaces;
  - `SecretStr` unwrapped only by a named private projection.
- **Already carried:** the node-HTTP error-classification contract file (`node-http-error-boundaries.json`) is also gone; that is covered by T3-D3.
- **The question:** should these conventions be consolidated into `package-layout.md`?

**nonpython-shared-skills-github-documentation-1-S1 — suggestion. This is about docs navigation.**
- PR 221's link to `python-formatting.md` is missing from `docs/architecture/README.md`, and its formatting section is missing from the root `README.md`.
- The doc is now reachable only through `AGENTS.md:26-28`.

**Carried forward:** all earlier T1–T5, C4–C6, nonpython-runtime-build and frontend findings.

## Not inspected

- Whether every model named in the exact-blob READMEs actually exists in `src`.
- Whether the frozen owner heads' copies of these docs differ from the final tree, except `AGENTS.md`.
- Whether the links inside `native-github-mediation.md` still resolve.