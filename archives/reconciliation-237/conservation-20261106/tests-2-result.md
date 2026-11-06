## Tests-2 conservation batch, plus the T1-D2R recheck

**BATCH_TESTS_2: COMPLETE.** All 62 header entries are classified. This is not an all-23 verdict or feature acceptance; all-23 stays HOLD, and nothing should be merged or closed from this batch. Four new narrow gaps came up (T2-D1 to T2-D4), and T1-D2R is now settled.

**Coverage and inputs:**
- **Ranges:** all seven ranges of `tests-2.txt` were read earlier in this session (1-200, 201-400, 401-600, 601-800, 801-1000, 1001-1200, 1201-1205). As you allowed, I didn't reread them this turn. The 62 headers came from a Grep over the whole file.
- **Guidance:** I read root `AGENTS.md` and Agent250's `AGENTS.md` by exact path.
- **D2R evidence:** I read `resume-20261106/controller-outcome-fix.diff` and `agent-controls-result.json`. That result reports head a79e3a8d, 95 tests, no failures or skips.
- **Method:** Read/Grep only. I ran no tests and recomputed no hashes.

## T1-D2R: SETTLED
- Both new tests are in the worktree, at `test_codex/test_acp_controller.py:166` and `:204`. I traced each against `controller/service.py:282-334`.
- **Missing terminal event, `:166-202`:**
  - The prompt records `turn/started` and then raises the safe code.
  - This reaches the branch at `:290-306`.
  - User cancel gives `("started-turn", "cancelled", "cancel_native_unconfirmed")`; timeout gives `("started-turn", "timeout", "turn_timeout")`.
  - `interrupt_acknowledged` stays False and `native_completion_status` stays None.
  - Events from earlier subtests don't leak in, because the controller reads from a per-call offset (`:258`).
- **Cancel with a failed or unknown terminal, `:204-232`:**
  - This reaches `:330-333` and gives `("turn", "cancelled", "cancel_native_unconfirmed")`.
  - The native status is kept, and `interrupt_acknowledged` stays False because it needs an `interrupted` status (`:311-313`).
- The old AppServer controller assertion is now kept at the right layer. No source changed.
- **T1-D2R-S1 (suggestion, not blocking):** two smaller branches have no test: the `unknown` status for a non-timeout failure after a started turn (`:303`), and a failure with no started turn being raised again (`:307-308`).

## Group classification
Paths are Agent250 unless stated otherwise.

| Entries (tests-2 line) | Status | Evidence / scope |
|---|---|---|
| Retirement/catalogue: 2, 16, 462, 474, 486 | PRESERVED | `test_codex/test_native_session.py:91-192` |
| Mailbox: 36 | INTENTIONALLY_SUPERSEDED (exp) | `tests/README.md:39-46`; redaction kept at `test_acp_controller.py:177-194` |
| Snapshot I/O error: 60 | PRESERVED | `test_runtime/test_lifecycle.py:111` (patch target only) |
| Opt-in git workspace: 74 | PRESERVED | `test_lifecycle.py`, same as tests-1 G8 |
| Constants migration: 112 | PRESERVED | Agent250 `test_shared/test_migration/test_paths.py:74` (`MANUAL_SYMBOLS`). The target-name check is correct when symbols are renamed (Shared255 `:69-115`). |
| LocalRunner probe worker: 134 | INTENTIONALLY_SUPERSEDED (exp) | Production no-cap contract: `test_lifecycle.py:1456-1473` and `:1475` |
| Catalogue routing: 172, 186, 719 | PRESERVED | `test_shared/test_errors/test_catalogue.py:143-237` |
| OpenCode history budget: 197 | PRESERVED | `test_opencode/test_history.py:166` |
| Dangling command plus cleanup failure: 210 | PRESERVED | `test_runtime/test_commands.py:188`. Helper `commands.py:22-38` keeps `item/started` and the close `OSError`. |
| Split preflight: 233 | PRESERVED | Settled as T1-D5 |
| Flags: 247 | PRESERVED | `test_shared/test_architecture/test_settings.py:107-126` |
| Stream settings: 259, 966 | PRESERVED | Settled as T1-D6 |
| Raw environment boundaries: 280, 987 | PRESERVED, minus negative guards (T1-S3) | Positive literals at `test_settings.py:170-188`. The `os.environ` guards on `claude/container.py` and `split/executor.py` were dropped. Source is clean today (`executor.py:32` uses an explicit `Client(environment=…)`), and endpoint behaviour is tested at `test_claude/test_login_session.py:235-258`. |
| Provider bindings: 301 | PRESERVED and extended | `test_protocol/test_provider_bindings.py` |
| Agent structure: 330, 358 | PRESERVED and stronger | `test_architecture/test_interfaces.py:57-79`, now with a non-empty scan check |
| Public contracts and base don't import concrete agents: 344 | Base PRESERVED; interface half GAP (**T2-D1**) | Base: `test_architecture/test_boundaries.py:36-62` |
| Retired provider/graph owners: 371 | GAP (**T2-D2**) | Only specific files are guarded (`test_protocol/test_boundaries.py:11-64`). Each provider is required to exist (`test_boundaries.py:84-91`). |
| Claude login: 381, 402, 432, 448 | Mostly PRESERVED; one dropped time bound (**T2-D4**) | `test_login_session.py:51-64` (refresh-capable login kept), `:87-105`, `:108-166`; `test_login.py:139-171`, `:266` |
| Evidence trace closure: 496 | PRESERVED | `test_codex/test_evidence.py:174-229`; the helper body is identical |
| exp104 live config: 528 | INTENTIONALLY_SUPERSEDED (exp) | Refusal before any provider contact: `tests/test_exp104_live_config.py:121-129`. Production credential handling: Shared255 `test_shared/test_git/test_command.py`. |
| exp104 S11 probe: 544 | INTENTIONALLY_SUPERSEDED (exp archive) | `tests/README.md:39-46` |
| Production turn cap: 553 | PRESERVED | `test_lifecycle.py:1456-1473` |
| Mediation startup: 567 | PRESERVED | `tests/test_mediation_service_startup.py:110` (root deferred suite, per `README.md:21-25`) |
| Historical graph blob manifest: 581 | INTENTIONALLY_SUPERSEDED | The examples are archived off-branch. The manifest remains as provenance (`tools/migrations/agent-history.json`). Refusal is enforced through `protected-graphs.json` (`tools/migrations/migrate_module_paths.py:882-892`) and tested in Shared255 `test_shared/test_migration/test_revisions.py:125-138`. The remaining asset is byte-pinned at `test_shared/test_architecture/test_cohesion.py:16-28`. |
| Reused package names: 596 | PRESERVED | Shared255 `test_paths.py:128` |
| Removed procedural Git APIs: 613 | Partly PRESERVED (**T2-D3**) | c8 `test_shared/test_migration/test_shared.py:157-236`; Agent250 `:159` |
| Historical CLI path refusal: 622 | PRESERVED | Shared255 `test_revisions.py:125-138` |
| Real stale-component cases: 634 | Mechanism PRESERVED; real cases UNVERIFIED (**T2-S1**) | `test_revisions.py:17-54`, `:140-185` (synthetic inputs) |
| Probe refusal identity: 653, 663 | PRESERVED for the probe module (**T2-S2**) | Shared255 `test_shared/test_migration/test_shared.py:124-130`; loader rewrite in `tests/support/retained.py:125-141` |
| Managed worker: 672 | INTENTIONALLY_SUPERSEDED (exp) | Same as tests-1 G11 |
| Poll timeout: 700 | INTENTIONALLY_SUPERSEDED (pending run kept, no resend) | `test_codex/test_native_timeout_reconciliation.py:281-327` keeps the active run in both the before- and after-deadline cases. Source: `interface/bridge.py:173-175`, `:226-228`. |
| Accounting / `_turn_available`: 733, 746 | INTENTIONALLY_SUPERSEDED; the rest PRESERVED | Absence asserted at `test_catalogue.py:758-763`; the helper survives only in the test harness `tests/test_agents/verification.py:21`; `test_runtime/test_accounting.py:17` |
| Retired module files can't return: 781 | GAP (**T2-D2**) | See T2-D2 |
| Canonical imports without forwarders: 791 | PRESERVED (**T2-S3**) | `test_shared/test_architecture/test_packages.py:59-76` |
| Persistent demo: 807, 827 | INTENTIONALLY_SUPERSEDED (exp139) | `tests/README.md:45`: budget contracts stay historical |
| Provider import boundaries: 866, 880 | PRESERVED and stronger | `test_boundaries.py:23-107` |
| Provider docker recovery: 896 | Same as T1-S1 | — |
| GraphQL query parity: 914 | PRESERVED | GitHub249 `tests/test_github/test_interface/test_reviewed_cli.py:19,86` |
| Sandbox: 924, 938, 952 | PRESERVED | `test_codex/test_sandbox.py` |
| Exception contracts: 1007 | PRESERVED and extended | `test_settings.py:191+` |
| Git profiles: 1040, 1054 | PRESERVED; the narrowing is justified | See the git profile notes below the table. |
| Generic Git scan: 1068 | PRESERVED | T2-I1 already approved |
| Verified stage: 1088 | PRESERVED | `test_host/test_publication/test_verified.py:524` |
| Work-graph grant: 1102 | PRESERVED | `tests/test_work_graph_launch.py:295` |
| Workspace skill Git: 1115, 1149, 1178 | PRESERVED (Agent250 is the complete version) | See the workspace skill notes below the table. |

**Git profile notes (1040, 1054):**
- Shared255 `git/models.py:23-26` has four profiles.
- The two isolated read profiles follow a different policy, and their exact environment is asserted separately at Shared255 `test_shared/test_git/test_read_budgets.py:59-110`.

**Workspace skill notes (1115, 1149, 1178):**
- Agent250 `test_agents/test_workspace/test_skill_exclusion.py:192-239` keeps `baseline_read.assert_not_called()` at `:206`.
- Skills254 `test_skills/test_workspace/test_exclusion.py:192-237` drops it.
- **T2-Q1 (question):** confirm that the combined branch keeps Agent250's stronger body.

## New findings
- **T2-D1 (defect, test conservation; owner Agent250; origin PR 216):** no test stops `agents/interface` from importing concrete providers or `agents.agents.base`.
  - Grep finds no such imports in `src/laomedo/agents/interface` today.
  - Replacement: a non-empty scan of `agents/interface/**/*.py` that forbids imports of `laomedo.agents.agents.{codex,claude,opencode,base}`.
- **T2-D2 (defect; owner Agent250 for the Agent directories; question about generic ownership):** old module paths and retired owner directories have no general guard against coming back.
  - What remains covers only:
    - specific files (`test_protocol/test_boundaries.py:11-64`);
    - files at the package root (`test_packages.py:53-57`);
    - the installed wheel, which is skipped when run from a checkout (`:20-51`).
  - `test_cohesion.py:118-128` checks that new targets exist, not that old ones are gone.
  - Replacement:
    - for each `module-paths.json` key, assert that the old `.py` file or package is absent;
    - assert that no `.py` exists under `agents/{providers,runtime,protocol,contracts,workflow,feedback,handoffs}` or top-level `activity`.
  - **Question:** Shared255's develop-based layout still has `agents/runtime/runner.py`, so the Agent-directory part belongs in Agent250 or the combined branch, not Shared255.
- **T2-D3 (defect, narrow; owner Agent250 manual-symbol data / Shared migration tool):** several manual-migration refusals from PR 216 have no test.
  - The untested forms:
    - `prepare_git_workspace`, listed at `tools/migrations/manual-symbols.json:17,23,44,47,56,76`;
    - `laomedo.agents.workspaces.git._bounded_git` (`:45`); only the singular `workspace` path is tested;
    - `_run_bounded_tree` via a module alias, an attribute and a nested attribute (`:59`).
  - The data exists; only the refusal tests are missing.
- **T2-D4 (defect, narrow; owner Agent250; origin PR 216):** the old `timeout == 20` check on the credential copy was dropped.
  - Copy time is now bounded in `claude/auth/utils.py`, through `COPY_SECONDS` in:
    - the normal deadline (`:126-128`);
    - the connection timeout (`:178-183`);
    - `StreamLimits` plus `deadline=` on the session (`:226-232`);
    - the wait (`:237`).
  - Tests assert only the context-inspect timeout (`test_login_session.py:105`) and `cleanup_seconds > 0` (`:164`).
  - Replacement:
    - assert the session `deadline` and `request.limits.seconds` are at most `COPY_SECONDS`, and the connection timeout is at most 20;
    - check that an expired deadline refuses with `claude_local_login_copy_failed` before the source is read.
- **T2-S1 (suggestion):** PR 216's six real stale-component cases (`pr-216.diff:19393-19446`) were replaced by synthetic inputs. Restore them as literal data if those saved graphs are still user-facing.
- **T2-S2 (suggestion):** only `native_managed_probe` has its refusal identity asserted; `native_managed_worker` and `probe_active_delivery` don't.
- **T2-S3 (suggestion):** the canonical-import test now skips on any missing `acp`, and `skipTest` abandons the remaining modules.
- **T2-S4 (suggestion):** the poll-timeout test doesn't count POSTs. The source structure shows there's no resend, so this is optional.
- **T1-S3 extended:** the dropped negative `os.environ` guards on `split/executor.py` and `claude/container.py`.

## Ledger and what I couldn't inspect
- **Closed:** T1-D1, T1-D2R, T1-D3, T1-D5, T1-D6, T2-I1.
- **Withdrawn:** T1-D4.
- **Open:**
  - this batch: T2-D1–D4 (defects), T2-Q1 and the T2-D2 ownership question, T2-S1–S4;
  - earlier batches: T1-D2R-S1, T1-D1-S1, T1-S1–S3, T2-I1-S1, C4-S1/S2, C5-S1–S3, C6-S1, and the OpenCode config gap (tools/share/autoupdate unasserted).
- **Not encountered in this batch:** findings 217 and 233 (233 was settled earlier).
- **Not inspected:**
  - test execution or hashes at a79e3a8d;
  - the combined head 1eb10a1f;
  - develop;
  - Skills254's own runner layout behind its weaker candidate;
  - c8 for most groups (Agent, Shared and GitHub heads were used instead);
  - hosted Black runs;
  - the TypeScript adapter's own preflight probe set (that's a non-Python packet).
- **Tooling limits:** one broad multi-worktree Grep timed out, and I narrowed it per head. Brace globs sometimes return nothing, so I confirmed absences with plain-directory Grep.

All-23 remains HOLD. Provider, browser, manual-publication and owner merge gates are separate, and no model execution was performed.