# Reconciliation of the separated refactor

This checkpoint preserves the recovery of work omitted while separating the integrated refactor. It is historical investigation evidence on `exp`, not a production integration branch or merge approval. Never merge this directory or `exp` wholesale into develop.

## Owning cuts

All PRs target restored develop `37dc9aa9f37304bc8b2c8e8e33b70e356b771764` and remain drafts.

| Concern | PR / branch | Pushed revision |
| --- | --- | --- |
| Shared records, bounded Git, preparation and offline migration | #255 `fix/237` | `939f1e08b2efe5602a9f08ec30186957f7ccb2a9` |
| Skill workspace, history, files and node/source controls | #254 `refactor/206` | `1c949341da6b49c0c85f5462a585cac270599d83` |
| GitHub modules, tests, examples and selected archives | #249 `refactor/245` | `3dbdac97dc682709d6cdcb5511f2fafa49da6c94` |
| Agent modules, providers, interface and host dependencies | #250 `refactor/205` | `ed8b771062b4a348da72fca3d3addcb9dbc34ca2` |

Original target: `8f7b184573cc0d6655d3b61a59f550d84e67253e` (refactor/237, PR238). Later mixed work: `3af136b054b8dcab9d879687bd64f343e0160601`. Actual detached cumulative validation tree: `a500adf73d2a19e57d92f827dfc5d220e8942095`. Accepted240 was restored by rollback253; develop is not overwritten by this recovery.

## What was recovered

Shared now retains ten host and eight Work Graph records, shared Git budgets/read isolation and owned Windows process containment, cleanup uncertainty/staging retention, direct imports and original offline migration mechanisms with later safety refusals. Source-owned cache behavior and `SkillRepositoryEntry` survive. The neutral graph helper and all real consumers use `examples/graph.py`.

Agent recovery retains the target `agents/agents/{base,codex,claude,opencode}` structure, public interface/output integration, module-level join handler, pinned Langflow admission, private-state contracts, native resource ownership, restored permission/activity/dependency regression cases and aligned lock. Latest Skill manual editing, binary assets, explorer/search/history and Source UI are retained. GitHub production tests no longer import prototype campaigns. A native CLI test uses the installed provider resource binding, preserving independent-cut and combined layouts.

The path ledger has 2996 original/later path-version entries and zero unresolved paths; all 162 original Agent and 47 GitHub source paths are present. Dispositions distinguish baseline, exact current blobs, changed/relocated implementations and exact historical archives. Definition accounting has 6218 entries with zero unclassified definitions. These classifications are review aids: matching method names do not prove assertion equivalence and changed code is not labelled unchanged behavior.

Only two original runtime definition names are deliberately absent: `BaseAgent._turn_available` (forbidden verification-only global gate) and `GitTreeEntry` (canonical source-owned `SkillRepositoryEntry` replaces the duplicate). Older mixed native CLI/HTTP/SSE implementations had already been retired by the original ACP target, rather than lost in the split. Their APIs are not asserted automatically compatible.

Of 72 latest mixed frontend inputs, 71 Git blobs are identical; the error catalogue is expanded. All 351 earlier codes survive in 418 current entries; seven existing explanations reflect later Agent hardening. The overlay installer blob is unchanged. See the explicit frontend/catalogue records.

## Experiments, examples and tests

Accepted240's EXP-08 removal remains. Skill viewer/summary campaigns (10 files), selected GitHub exp108/issue-integration campaigns (16 files) and selected Agent exp10/exp117 campaigns (17 files) are absent from their owning production cuts only after exact preservation. Other 552 legacy Agent campaign/dependency files remain explicitly deferred: this checkpoint does not claim the entire experiments directory was removed.

Original and later campaign/example/test/proof variants are preserved under earlier `archives/reconciliation-237` manifests at exp `0f66ebb560c2b9d916ddeb3c0c6d54291642bbf0`. Raw Git blob identities, rather than newline-normalized exports, establish historical fidelity. Archive preservation is not active regression coverage. Accepted240's removed source-body proof snapshots are not restored to production. Missing substantive security/admission cases identified by the audit are current concern-owned tests; obsolete prototype-only import-identity scaffolding stays historical.

## Validation and remaining gates

See [verification-summary.json](verification-summary.json) and [hosted-checks.json](hosted-checks.json). Independent Shared discovery ran 1,132 tests (21 skips), Agent source recovery 1,180 (10 skips), and the self-contained normally installed cumulative runtime 1,287 (19 skips), with no failures. Final installed changed controls at `a500adf73d2a19e57d92f827dfc5d220e8942095` ran 151 GitHub (1 skip), 43 migration, 19 Agent architecture and 26 package architecture tests without failures. The final production source/components/frontend/package metadata are byte-identical to the full installed runtime; later test-only checks are recorded separately. All 32 configured exact-head hosted checks across the four cuts pass.

Real headless Edge checks used 18 retained history entries and the actual local my-skills checkout: per-file history diff, search tree, image preview/full-page restore, typing/discard, empty-source affordance, actual forbidden local-source failure and recovery. No responses were intercepted, models run, credentials copied or registry revisions published. Screenshots/runtime state remain private local evidence; they are not in this archive. These bounded stories do not establish full provider or owner acceptance.

Shared code has exact-head Claude approval. The final conservation/recovery review was actually attempted in the retained reviewer session and ended at its subscription limit (reported reset 23:10 Europe/Berlin on 2026-11-03); no final verdict was obtained. Final independent conservation/delta and visual review, natural cleanup-uncertainty UI evidence, outstanding Agent feature/spec/provider gates, and requesting-owner final graph validation remain explicit. No PR was merged.

After approval, merge Shared first, incorporate actual develop into each remaining owner cut, then review resolutions and rerun affected checks. Do not use this cumulative tree as a stacked production PR or bypass ownership by merging exp.

## Recover the exact cumulative tree

The small bundle stores the local-only resolution commits; all 21 prerequisites are ancestors of the four pushed owner branches. [bundle-prerequisites.json](bundle-prerequisites.json) gives the exact reachability proof. First fetch the owning branches from the upstream repository, obtain this archive from exp in a separate worktree, then verify and fetch the bundle:

```powershell
git fetch origin fix/237 refactor/206 refactor/245 refactor/205
git bundle verify <archive-path>/reconciliation-resolution.bundle
git fetch <archive-path>/reconciliation-resolution.bundle HEAD
git worktree add --detach <new-review-worktree> FETCH_HEAD
git -C <new-review-worktree> rev-parse HEAD
# Expected: a500adf73d2a19e57d92f827dfc5d220e8942095
```

Use a fresh path and preserve other checkouts. The bundle contains tracked code/history only, never the private preview database, browser profile, credentials, logs or model state. [manifest.json](manifest.json) seals each archive file with its byte count and SHA256; earlier provenance manifests retain original Git blob/mode records.
