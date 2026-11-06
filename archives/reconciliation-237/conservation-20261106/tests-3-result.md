## Tests-3 conservation batch

**BATCH_TESTS_3: COMPLETE.** All 66 header entries are classified into 31 contract groups. This is not an all-23 verdict or feature acceptance; all-23 stays HOLD, and nothing should be merged or closed from this batch.

Most groups are preserved, with record literals spot-checked against the original captures. Six new gaps came up; the most important is **T3-D4**: the HTTP listeners' token and loopback admission checks are no longer tested anywhere.

**What I read:**
- All seven ranges of `tests-3.txt`, this turn: 1-200, 201-400, 401-600, 601-800, 801-1000, 1001-1200, 1201-1206.
- The full header list via Grep.
- Root `AGENTS.md` (retained) and Agent250's `AGENTS.md`, which I read by exact path last turn.

**Method:** Read/Grep only. I ran no tests and recomputed no hashes.

## Group classification
Each path is in the owning head (Shared255 = `.tools/shared-reconciliation-237`, which also holds the Skills tests; GitHub249; Agent250).

| Entries (tests-3 line) | Status | Evidence / scope |
|---|---|---|
| A. 217 GitHub records: 2, 19 | PRESERVED (217 confirmed restored) | GitHub249 `tests/test_github/test_contracts/test_values.py:24-112`. Covers admission codes, redaction of `private-invalid-value`, exact order, digest preimage and label non-aliasing. |
| B. Skill revision/draft/frozen record: 35 (PR 218, LF), 620 (PR 220, CRLF) | PRESERVED | Shared255 `tests/test_skills/test_registry/test_store.py:514` holds the PR 220 CRLF literal. The earlier LF version's hashes are covered by the LF/CRLF test at `:470`. |
| C. Commit IDs and comparison: 76 | Commit preimages and replay PRESERVED; comparison GAP (**T3-D1**) | `tests/test_skills/test_operations/test_preimages.py:11-88` (exact IDs, field order, stored JSON); replay at `test_service.py:41-48` |
| D. Agent prepared/status/request records: 100, 150, 177 | PRESERVED | Agent250 `test_runtime/test_preparation_records.py:13`, `test_interface/test_records.py:10`, `test_orchestration/test_request_records.py:12`. Spot hashes match the originals: request digest at `pr-217.diff:744`; prepared hashes at `pr-219.diff:1224-1243`. |
| E. Models class-only and fields described: 201, 595 | Class-only PRESERVED; descriptions GAP (**T3-D2**) | Class-only is enforced across the whole tree by `test_shared/test_architecture/test_cohesion.py:77-90`. Descriptions are checked only for Shared/host/work-graph/git models (Shared255 `test_restored_records.py:10-86`). |
| F. Interface models stay a dependency leaf: 216 | GAP (folded into **T2-D1**) | `agents/interface/models.py` has no `laomedo` imports today, but nothing guards it. |
| G. Component keeps its docstring: 225 | Unguarded (**T3-S1**) | — |
| H. Join handler module-level; no giant constructors: 233 | Module-level and nested-class parts PRESERVED; giant-dict ban lost (**T3-S1**) | Agent250 `test_agents/test_architecture/test_join.py:12-31`, `test_interfaces.py:57-71` |
| I. Lease client: 248, 262; mediation startup: 278 | PRESERVED | Same as tests-1/tests-2 |
| J. Gateway intent hashes: 292; feedback snapshot: 340 | PRESERVED | GitHub249 `test_contracts/test_intents.py:14`, `test_pull_requests/test_feedback.py:174` |
| K. Work grant CLI: 405; work launch preimages: 547 | PRESERVED | Shared255 `tests/test_work_graph/test_records.py:17,184`. Fixture IDs match `pr-220.diff:7429-7430`. |
| L. Container identity: 477; lease window: 499 | PRESERVED | Agent250 `test_host/test_leases/test_records.py:24,45` |
| M. Claude telemetry environment: 533 | PRESERVED | Agent250 `test_agents/test_claude/test_records.py:13` |
| N. Verified stage preimages: 565 | PRESERVED | Shared255 `test_host/test_publication/test_records.py:18`. Digests match `pr-220.diff:7396,7411`. |
| O. Work-graph models documented: 610 | PRESERVED | `test_restored_records.py:29-38` |
| P. LF vs CRLF stay distinct revisions: 662 | PRESERVED | `test_store.py:470` |
| Q. `lease_controls.result` retries: 716, 724, 731 | INTENTIONALLY_SUPERSEDED (it was a test helper) | See the lease-reader notes below the table. |
| R. Scan rechecks time after a stall: 739 | PRESERVED | `tests/test_mediated_lease.py:309`. The dropped `loss_seconds = 0.5` is now set in `setUp` (`:79`). |
| S. Golden handler AST digests: 759, 1185 (PR 224 later version); canonical-AST tool: 857 | INTENTIONALLY_SUPERSEDED (opaque proof) | The admission check the digest pinned has no behavioural replacement (**T3-D4**). |
| T. No nested classes or module aliases: 782 | Partly PRESERVED (**T3-S1**) | Skills: `test_skills/test_interface/test_ownership.py:10-22`. Agents: `test_interfaces.py`. No guard for the GitHub or HTTP modules. |
| U. Redirect owners: 794; redirect refused: 899 | PRESERVED (**T3-S3**) | Shared255 `test_shared/test_http/test_redirects.py:32-43`, `:51-83` |
| V. Retired redirect targets: 805; identity alias: 841; alias guard: 849 | Partly PRESERVED; identity alias INTENTIONALLY_SUPERSEDED | Migration is one-pass (`test_shared/test_migration/test_shared.py:104-122`); the retired module is absent (`test_redirects.py:83`); the loader rewrites `_NoRedirect` (`tests/support/retained.py:142-149`). Scanning example and component code is lost (**T3-D6**). |
| W. Skill clients stay domain leaves: 872 | PRESERVED as a static check | `test_ownership.py:10-34` |
| X. Server isolation, safe fallbacks, domain codes, client projections: 880, 912, 926, 937 | PRESERVED | See the server-behaviour notes below the table. |
| Y. Catalogue and manifest guards: 953, 968, 977, 990, 1010 | Partly PRESERVED (**T3-D3**) | GitHub: `test_github/test_contracts/test_errors.py:13-47`, including the "before authorizing another" recovery check. Source codes: Shared255 `test_skills/test_sources/test_errors.py:11-91`. |
| Z. Constants migration: 1030 | PRESERVED | Same as tests-2 |
| AA. Ingestion is an exact symbol-only move: 1043 | INTENTIONALLY_SUPERSEDED (opaque AST proof) | Behaviour: `test_host/test_publication/test_ingestion.py:54-257` |
| AB. Ingestion ownership and prior generations: 1057 | PRESERVED | `test_shared.py:21-62`, `test_cohesion.py:118-128`, `test_ownership.py:36-51`, and the generic exception contracts in `test_shared/test_architecture/test_settings.py` |
| AC. No retired ingestion imports in callers or examples: 1082, 1101 | GAP (**T3-D6**) | — |
| AD. Retained probe migration changes only imports: 1118 | PRESERVED (question **T3-Q1**) | The loader refuses any non-import change (`support/retained.py:178-201`). |
| AE. Helpers have no module aliases or mixed objects: 1136 | PRESERVED | `test_cohesion.py:77-116` |
| AF. Ingestion error codes; mediation refusals: 1145, 1164 | GAP (**T3-D5**) | — |

**Lease-reader notes (Q):**
- The product reader `_read_json` is in Agent250 `src/laomedo/host/leases/utils.py:214-224`.
- The lock retry is tested at `test_host/test_leases/test_service.py:153-168`.
- An absent result fails closed with `lease_service_unverified` (`test_agents/test_runtime/test_failure_observations.py:320`).
- One difference: a malformed result now returns None (and eventually fails closed) instead of raising. See T3-S2.

**Server-behaviour notes (X):**
- GitHub: `test_github/test_interface/test_bindings.py:34-64`, `test_issues/test_http.py:112`, `test_pull_requests/test_http.py:66,99`.
- Skills: Shared255 `test_skills/test_interface/test_http.py:44-118`.

## Findings
- **T3-D4 (defect, security admission; owners GitHub249 and Shared255; origin PR 222/224):** no test checks that the four listeners refuse a non-loopback host or a bad token.
  - The checks themselves:
    - GitHub249 `github/interface/issues/server.py:11-12` and `pull_requests/server.py:11-12`;
    - Shared255 `skills/interface/sources/server.py:12-13` and `operations/server.py:12-13`, which also enforce at most 512 characters.
  - The removed AST digest was the only thing pinning these. No head tests any `private_*_service_required` code.
  - Replacement: for each server, a token that is too short, not a string, or (for operations) longer than 512 characters, and (where applicable) `host != "127.0.0.1"`, raises the exact code before a socket is bound.
- **T3-D5 (defect; owner Shared255; origin PR 223):** the `bundle_freeze` outcome mapping isn't directly tested.
  - At `host/mediation/store.py:613-639`, a freezer result of `refused` becomes `{"state": "rejected", "error": code}`. Any raised error, including `BundleIngestError`, becomes `{"state": "unknown", "resent": False}`.
  - Nothing asserts the four exported refusal codes (`bundle_not_regular`, `bundle_size_or_type`, `bundle_changed_or_oversized`, `bundle_unreadable`), that raised secrets don't leak, or that those codes have catalogue entries.
  - The entries do exist today (catalogue lines 2107-2122). The ingestion tests only check `result["reason"]`.
  - Replacement: port the PR 223 mock-freezer test (`pr-223.diff:1513+`) and the catalogue check for the exported codes.
- **T3-D1 (defect, narrow; owner Shared255; origin PR 218):** the exact `compare()` payload is no longer pinned.
  - That covers key order, `base_commit` without `patch` (`skills/operations/service.py:389`), and the per-file `{path, status, before_hash, after_hash, binary}` shape.
  - The tests check only parts of it (`test_service.py:233-338`).
  - Replacement: the original literal at `pr-218.diff:1353+`.
- **T3-D2 (defect, narrow):** described-field checks were dropped outside Shared/host/work-graph/git.
  - Not covered: GitHub (`issues`/`pull_requests`/`github` models), Skills (`registry`/`operations` models), Agent (`artifacts`, `orchestration`, `base`, `interface`, `activity`, Claude/OpenCode activity, OpenCode models) and `host.leases.models`.
  - Each owner should carry its own check.
- **T3-D3 (defect, narrow; owners Shared255 Skills interface and GitHub249):** parts of the HTTP catalogue guard are gone.
  - Nothing guards the catalogue coverage or no-blind-retry recovery text for the Skill operation client and handler codes: `skill_operation_unavailable`, `skill_operation_service_not_configured`, `skill_operation_refused` (sources at `skills/interface/operations/client.py:27,49` and `handler.py:30,58`). The entries exist today at catalogue lines 2077-2091.
  - Nothing checks that every handler's `error_category` literals are public catalogued codes.
  - Nothing checks that the PR client filters on `PR_CODES`, which excludes `github_http_*`, unlike the issue client.
- **T3-D6 (defect, narrow; owner Shared255):** the repository-wide scan for retired redirect and ingestion imports in components, example-graph embedded code and tests is gone.
  - What remains covers only direct imports of `skills.sources.transport` in src and components (`test_redirects.py:54-71`).
- **T2-D1 extended:** it now also covers keeping `agents/interface/models.py` free of `laomedo` imports.
- **T3-S1 (suggestion):** add structural guards for:
  - the giant-dict constructor ban (≥10 keys) in `_prepare`/`envelope`;
  - the component module docstring;
  - nested-class and module-alias checks for the GitHub and HTTP modules.
- **T3-S2 (suggestion):** test `_read_json`'s retry on `FileNotFoundError`, and that a malformed result returns None.
- **T3-S3 (suggestion):** the redirect-owner test finds classes by name (`NoRedirect`/`_NoRedirect`), not by `HTTPRedirectHandler` base class, so a renamed redirect handler would go unnoticed.
- **T3-Q1 (question):** `retained-ingestion-callers.json` and `retained-http-callers.json` no longer exist in Shared255. Confirm that any retained ingestion or HTTP callers are listed in `retained-shared-callers.json`.

## Ledger and what I couldn't inspect
- **Open after this batch:**
  - tests-3: T3-D1 to T3-D6, T3-S1 to T3-S3, T3-Q1;
  - tests-2: T2-D1 (now extended), T2-D2 to T2-D4, T2-Q1, T2-S1 to T2-S4;
  - tests-1: T1-D2R-S1, T1-D1-S1, T1-S1 to T1-S3, T2-I1-S1;
  - runtime batches: C4-S1/S2, C5-S1 to S3, C6-S1;
  - the OpenCode config gap (tools/share/autoupdate unasserted).
- **Closed:** T1-D1, T1-D2R, T1-D3, T1-D5, T1-D6 and T2-I1; T1-D4 is withdrawn. 217 is confirmed restored; 233 was settled earlier and isn't in this batch.
- **Not inspected:**
  - test runs and hashes at the reverified heads;
  - full byte equality of the restored literal data files (I spot-checked hashes against the original diffs only);
  - develop and 1eb10a1f;
  - Skills254's own test tree beyond name searches (its Skills tests live in Shared255 and c8);
  - c8, except for name lookups;
  - catalogue text in GitHub249's own catalogue file.
- **Tooling limits:** two broad multi-worktree searches timed out; I narrowed them to single heads.

All-23 remains HOLD. Provider, browser, manual-publication and owner merge gates are separate, and no model execution was performed.