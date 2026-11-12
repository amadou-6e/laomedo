# Final packet: docs, maps, deployment, focused test recheck and integration accounting

**Bottom line:** M01, T-01 and Q-T1 are fixed and verified, and I found no new defect in the docs, maps or deployment changes I read. But I can't call the integration review complete: several files that differ from develop don't appear in any packet I can map, and some packet artifacts weren't read. Code approval and native/owner acceptance remain separate, and no merge or issue closure is authorized.

## Corrections in b6f6dbfb

**M01: resolved.** The guides now match the current runtime:
- `codex/settings.py:5` sets `IMAGE = "laomedo-codex-acp:0.159.2-2.1.1"`, and `docker/images.json:17-19` registers that tag with the `codex-acp` context and `codex-cli 0.159.2` verification.
- `docker/README.md:6-7,21-23` says DockerRuntime builds only missing registered images, refuses mismatched recipes, and fails a missing or mismatched explicit pin without building.
- The new wording in `local-app.md` and `docker/codex-acp/README.md` agrees with those rules.
- `RunnerService.config` (read earlier) accepts `image_id` only for Codex without `git_workspace` and only in strict `sha256:` form, which matches the guide.
- The bare-CLI `docker/codex` recipe is removed, not registered, and no longer linked from the current guide.
- I did not verify the exp archive (ee600c27); I relied on your statement.

**T-01: resolved.** The filter is back to the plural `laomedo.agents.workspaces.skills.`. Each of the three target groups now has its own subTest asserting it is non-empty, so a future typo would fail rather than silently drop a group. No historical counts are pinned.

**Q-T1: resolved.** Only `integrations.langflow.launch.settings` is exempt. Every other `int`/`float` field now asserts a string `validation_alias` instead of being skipped, and the original environment checks are kept. I relied on your log (`t01-qt1-checks.log`, 14 passing) and did not re-enumerate the settings classes myself.

## Findings in this packet

**No confirmed defects.** Optional cleanup only:

- **D-03 (optional, docs):** these links point at the spec branch `feat/410`, which has since merged as 3d6ff823:
  - `docs/features/authentication/README.md:389`;
  - `local_profiles/README.md`.

  The links may break once the branch is deleted; point them at the merged main path.
- **D-04 (optional, docs):** these docs inherited from develop still describe profiles as "PR #263 draft", which is out of date now that the work sits in PR250:
  - `authentication/local-profiles.md`;
  - `authentication/verification.md`.

  The embedded Codex component comment still says old saved Claude/OpenCode code "must migrate its base", though the migration tool is gone. These are wording issues, not behaviour.

**What I checked in the docs and maps, with no issue found:**
- **Example graphs:**
  - The ten recorded non-code changes cover the Agent `task` input: `StrInput` accepting Message and Data, the matching handles, and `trace_as_input` dropped. They agree with the fixture change in `test_graph/agent.py` and with the digests in `component-templates.json`.
  - The embedded Codex and Skill source changes are limited to the `Settings().codex_runner_url` default and the `utils.proposal` import, with refreshed `code_hash` values.
- **PR builders and walkthroughs:** the `examples/github/build_flow.py` edges (`pr`→`task`, `answer`→`pr_context`) and the walkthrough text match the single-port contract that `pr.py` enforces.
- **Maps:**
  - `module-paths.json` adds the new current owners: `host.http`, `git.credential_helper`, `github.workflows`, `credentials.token`, `registry.utils.*`, `operations.utils.summary`.
  - It correctly drops `skills.operations.settings`, which is now a current module, so the retired-import check doesn't flag it.
  - The executable migration tool, `cli-paths.json`, `manual-symbols.json`, `migration_errors.py` and the legacy contract migrator are removed, and the README describes the remaining JSON as internal data.
  - `load_owner_maps` only reads that data.
- **Lost protection:** none found. The current invariants are still tested: the concrete adapter guard, retired-import ownership, owner-target resolution (now covering all three groups) and refusal of historical probes. The deleted tests only exercised the retired tool.
- **Deployment:**
  - `pyproject.toml` adds the `laomedo-app` entry point, matching the guide.
  - `start_local_profiles.ps1` was reviewed as integrated develop content. Its anchors are consistent with `test_setup.py`.
- **AGENTS.md:** the lifecycle and UI-handoff sections are consistent with the retirements in this PR.

**Remaining tests:** `remaining-tests-equivalence.json` shows `test_summary.py` and `test_registry/test_inspection.py` hash-identical to develop, so they are not own behaviour. I did not read their bodies. Their imports, which I read earlier, bind to the current owners.

## Integration accounting: incomplete

`own-stat.txt` lists 775 files against develop. The provider-feature files were covered by the earlier review through 6cff259a, and the later delta by core packets 1–3, the generic-imports packet, the tests packet and this one. But I can't match these own-vs-develop paths to any packet artifact that was reviewed:

| Path | Diff size vs develop | Notes |
|---|---|---|
| `src/laomedo/integrations/langflow/stage_adapter.py` | 90 lines | Not in any packet diff. Possibly part of the original provider feature. |
| `src/laomedo/github/pull_requests/context.py` | 10 lines vs develop | imports.diff only showed it as new relative to the 8fe parent, so the develop-relative delta was not reviewed. |
| `.github/workflows/work-graph.yml` | 23 lines | |
| `setup.py` | +47 | |
| `MANIFEST.in` | +2 | |
| `uv.lock` | 22 lines | |
| `tools/migrations/protected-graphs.json` | +9 | |
| `symbol-paths.json` | 1255 lines | Map body not read line by line. Only checked indirectly through the retired-import and owner-resolution tests. |

Some of these may be inside the earlier 6cff259a feature review. That isn't recorded in this conversation, so I can't claim it.

**Not read in this packet:**
- `docs-combined.diff`, `docs-paths.json`, `metadata.json`, `integration-findings.md`;
- `docs.diff` lines 920–1099 (deleted `migrate_legacy.py` and the workgraph-demo `flow.json`, which follows the same recorded regeneration pattern), 1323–2324 (body of the deleted tool) and 2475–3235 (rest of `symbol-paths.json`);
- carried over from earlier packets: `imports-combined.diff`, `tests-combined.diff`, `tests-paths.json`, `imports-final-unread.diff` (that gap was closed through the hash evidence).

## Verdicts

- **Code:** No blocking defect in the scope I read; M01, T-01 and Q-T1 are resolved. The overall integration verdict is **INCOMPLETE** until the paths in the table above are mapped to a prior review or reviewed now.
- **Spec:** No spec delta in this packet. Specs remain merged at 3d6ff823.
- **Docs:** Acceptable, with optional D-03 and D-04.
- **Visual:** Unchanged. APPROVE stands only for the earlier Skill default/Advanced, Prior Run and PR layout captures, not for profile, recovery or live GitHub screens.
- **Acceptance:** Real owner-graph and native acceptance are still pending.

**Reviewer status:** b6f6dbfb is reviewed for the scope listed above. The unmapped paths in the table have not been reviewed in this conversation, so the review is incomplete; no merge or issue closure is authorized.