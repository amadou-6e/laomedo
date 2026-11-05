# BATCH_RUNTIME_5: COMPLETE

All 46 header entries in `runtime-5.txt` are covered, across PRs 216, 218, 220 and 222. All 15 contract groups are **PRESERVED**; I found no defects, no supersessions to verify and no gaps that block. There are three low, optional suggestions. Reading the ranges and finding matching source and tests is coverage, not semantic proof: I ran nothing. This is not an all-23, feature, merge or closure verdict, and the all-23 verdict stays **HOLD**.

**Ranges I actually read from `runtime-5.txt`:** 1–200, 201–400, 401–600, 601–800, 801–1000 and 1001–1183.

**Root `AGENTS.md`:** I relied on the section I read earlier (lines 34–49) and did not reread it.

**Entries covered** (class-level entries and their method-level versions were each checked):
- **PR 216 (22 entries):**
  - `GitCommandRunner` `.environment`, `._arguments`, `._execute` and `._stop_tree`
  - `GitEnvironmentProfile`, `GitExecutionContext`, `GitCommand`
  - `RunGrantAuthority`; mediation `cli.main`
  - `HandoffStore` and `.freeze_publication_handoff`; `resolve_verified_stage`
  - `JoinServer` and `.__init__`
  - `FrozenLangflowStage` and `.__init__`
  - viewer `install_routes`
  - `LocalGrantAuthority` and `.__call__`
  - `relevant_content_digest`, `preflight`, `launch_local_saved_flow`
- **PR 218 (13 entries):**
  - `FileEdit`, `.validate_path`, `.validate_content`
  - `SkillProposal` and `.from_payload`
  - `SkillCommit`
  - `SkillOperations`, `.prepare`, `.apply`, `.history`, `.diff`
  - `SkillStore` and `.import_skill`
- **PR 220 (8 entries):**
  - OpenCode projection `project`
  - `GitHubIssueGateway` and `.execute`
  - `GitHubPRGateway` and `.execute`
  - `OAuthAuthorizationRequest`, `OAuthAccount`
  - `LeaseService._publish_heartbeat`
- **PR 222 (3 entries):** `skill_request`, `SkillOperationRequestHandler` and `.do_POST`. The batch marked the handler entries "no direct normalized owner", so I traced them through the raw diff (see G15).

**Owners:** assigned from where the defining files are present. Several files also appear in more than one develop-based worktree, so this attribution is by package, not by exclusive presence.
- **Shared255:** `git/*`, `host/*`, `work_graph/*`
- **Skills254** (`skills-followup-206`): `skills/*`, the viewer and skill editing
- **GitHub249:** the GitHub gateways
- **Agent250:** the join handler, the Langflow stage adapter and the OpenCode projection

Evidence below is from c8 (`.tools/reconciliation-integration-237`) unless another path is given.

## Results by contract group

| # | Contract group (entries) · owner | Status | Current evidence |
|---|---|---|---|
| G1 | Isolated read-only git profiles: new enum values, `hooks_path`, `cwd`, `budget`, profile validator (entries 1–7; runner code was already covered in runtime-4) · Shared255 | **PRESERVED** (see C5-S1) | `git/models.py:25-26, 93, 160-203`.<br>`test_shared/test_git/test_read_budgets.py`: `:46-57` (command fixture), `:59-110` (exact environment and argv), `:112-142` (rejected overrides; invalid commands never reach Popen). |
| G2 | `AuthorizedLeaseScope` and `MediationServiceRecord` · Shared255 | **PRESERVED** | `host/mediation/models.py:6-64`; `authority.py:236-259`; `cli.py:120`; `host_services.py:121`.<br>The scope is still built after the `lease_token` UPDATE, as before. The relevant columns are `NOT NULL` (`authority.py:50-56`).<br>Test: `test_mediation/test_records.py:68-96` (field omission, Python set, integer PR keys). |
| G3 | Publication request and verified-stage identity · Shared255 | **PRESERVED** | `handoff/models.py:7-28`; `store.py:146` stores it through sorted-key `_json` (`handoff/utils.py:14-18`); `verified/utils.py:333`.<br>Test: `test_publication/test_records.py:18-45` (captured active and frozen preimages and digests), `:78-84`. |
| G4 | Join HTTP handler moved from a closure to a module (13–14) · Agent250 | **PRESERVED** | `join/handler.py:11-159` keeps the same routes, bearer `compare_digest`, sorted JSON replies, 409/502/400 mapping, 64 KiB body limit and exact field set. `server.py:8-18`.<br>Status responses still use `RunnerStatusRecord`, which runtime-4 confirmed against a literal fixture.<br>Test: `tests/test_langflow_join_http.py:87-196` (401 without token, 409 on a changed retry, cancel, redirect doesn't forward the token). |
| G5 | Langflow runtime pin now also accepts `langflow-base` (15–16) · Agent250 | **PRESERVED** | `stage_adapter.py:23-55`; `test_work_graph/test_langflow/test_runtime.py:37-64` (every combination of present and missing distributions). |
| G6 | Viewer registers manual skill routes and `include_binary` (17) · Skills254 | **PRESERVED** | `viewer.py:14-22, 105`; `skill_editing.py:8-44` (action allow-list, same-origin check, 4 MiB cap, error codes from a fixed set); `test_skills/test_inspection/test_bundle.py:86-222`. |
| G7 | Work-graph grant, launch, content-digest and result records (18–22) · Shared255 | **PRESERVED** | `grants.py:126`; `launch.py:50, 126`; `local_launch.py:56`; `work_graph/models.py:269-460`.<br>Tests in `test_work_graph/test_records.py`:<br>• `:17-110`: literal redeemed grant, expiry, no redemption on expiry.<br>• `:112-182`: ordered result keys, no output leak.<br>• `:184-199`: captured launch preimage and digests in `fixtures/launch-record.json`.<br>Also `test_launch.py:173-176` (override). |
| G8 | `FileEdit`/`SkillProposal` base64 and copy-from-base forms (23–27) · Skills254 | **PRESERVED** | `skills/operations/models.py:34-211`.<br>Tests in `test_skills/test_operations/test_binary.py`:<br>• `:16-33`: legacy text request keeps its exact hash.<br>• `:35-59`: only canonical base64, no mixed forms, size cap, no path escape.<br>• `:61-129`: changes apply atomically, with no partial history. |
| G9 | Durable `import.json`, import-history backfill, `revision_lineage`, legacy empty root patch (28–35) · Skills254 | **PRESERVED** | `skills/operations/service.py:105-338`; `skills/registry/store.py:152-216`.<br>Tests: `test_skills/test_operations/test_import_history.py:30-204` (durable before use, concurrent and repeat calls don't duplicate, legacy backfill stable, legacy IDs not rewritten, interrupted import keeps one event); `test_skills/test_registry/test_store.py:393` (`import_busy`). |
| G10 | OpenCode projection via `ActivityProjection.to_usage_first_payload` (36) · Agent250 | **PRESERVED**; finding 233 confirmed present (see note) | `agents/activity/models.py:208-227` uses the original key order; `opencode/activity/projection.py:390-414`.<br>Restored in the owning worktree `.tools/agent-refactor-205`: `tests/test_agents/test_activity/test_envelope.py:21-32` compares exact key lists and `json.dumps` bytes for the eight cases in `data/projector-records.json`. |
| G11 | GitHub gateways: `pr_digest` → `issue_digest`; intent construction failure → `*_grant_unavailable` (37–40) · GitHub249 | **PRESERVED** (see C5-S2) | `github/pull_requests/contract.py:8` defines `pr_digest = issue_digest`, so every digest is unchanged. Gateways: `issues/gateway.py:160-166`, `pull_requests/gateway.py:65, 286-301, 336-344, 409`.<br>Finding 217, restored in `.tools/github-restored-245` `tests/test_github/test_contracts/test_values.py`: `:24-40` (public error codes, invalid private value not echoed), `:42-112` (payload order, Unicode hash preimage, `assertIs(pr_digest, issue_digest)`), `:114-138` (intent preimages). |
| G12 | OAuth `ext_agent_host_id` becomes a JSON value excluded from ordinary dumps (41–42) · Shared255 | **PRESERVED** | It is still sent where needed: explicitly in `to_query` (`siwc/models.py:59-74`) and `to_private_record` (`:208-223`).<br>Tests: `test_siwc/test_records.py:32-64, 178-190` (ordered keys), `:219-234` (in the query, absent from `model_dump`); `test_chatgpt.py:152`. |
| G13 | Lease heartbeat logs the failing stage and re-raises (43) · Shared255 | **PRESERVED** (see C5-S3) | `host/leases/service.py:74-85`; `utils.py:22-31`; `test_failure_observations.py:187-194` (log never contains the message or filename). |
| G14 | `skill_request` manual actions and error mapping (44, file moved to `skills/interface/operations/client.py`) · Skills254 | **PRESERVED** | `client.py:14-74`; generic client error projections tested in `test_skills/test_interface/test_http.py:94-118`. |
| G15 | `SkillOperationRequestHandler` and `.do_POST` (45–46; no normalized owner) · Skills254 | **PRESERVED** (moved and extended; not a retirement, not related to ACP) | **Original:** `pr-222.diff:1638-1698` is a pure extraction of the closure at `:1724-1772`.<br>**Current:** `skills/interface/operations/handler.py:11-112` keeps bearer `compare_digest`, the JSON content-type check, the 4 MiB cap, exact path and field sets, and the redacted `skill_operation_refused` for the original five routes. It adds the editor/save/publish routes with mapped manual error codes.<br>**Tests:** `test_http.py:44-80` (per-instance tokens, 401, redaction); `test_skills/test_operations/test_service.py:198-217` (401; an injected extra `policy` field is rejected). |

**Finding 233 note:** I compared the restored file with the original export (`original-activity-projection-records.json`). Both have the same eight case names and projectors. Key lists match for `shared-empty` and `opencode-native`. Partly decoding the base64 of those two cases matched the restored `expected_json` at the start, the middle and the end. I did not decode or hash the other six cases.

## Findings (all optional, non-blocking)

**C5-S1 / suggestion / low**
- **Location:** `git/models.py:179-202`. **Owner:** Shared255. **Origin:** PR 216.
- **Untested branches:** no test in c8 or `shared-reconciliation-237` exercises:
  - `git_read_profile_required`, which rejects `budget` or `cwd` on a non-isolated profile;
  - an isolated profile with `hooks_path=None` or `hardened=True`;
  - empty `arguments`;
  - the `--` operand terminator.
- **Mechanism:** `_execute` takes the budgeted path for any command that has a budget (`command.py:164-165`). If the guard were removed, a write-capable profile could silently gain the read-only `cwd`/budget path without any test failing.
- **Suggestion:** add these rejection cases next to `test_read_budgets.py:112-134`.

**C5-S2 / suggestion / low**
- **Location:** `issues/gateway.py:160-166`; `pull_requests/gateway.py:286-301`. **Owner:** GitHub249. **Origin:** PR 220.
- **Issue:** redaction is tested at the model level (`test_values.py:24-40, 137-138`). I found no test showing that a rejected `GitHubOperationIntent` inside `execute` becomes exactly `issue_grant_unavailable` or `pr_grant_unavailable`, with no private value in the error.

**C5-S3 / suggestion / low**
- **Location:** `host/leases/service.py:74-85`. **Owner:** Shared255. **Origin:** PR 220.
- **Issue:** no c8 test references `_publish_heartbeat`. Only the logger itself is tested.
- **Consequence:** a regression that logged the wrong stage, or swallowed the `OSError` instead of re-raising it (which would hide heartbeat loss), would not fail any test.

## Earlier clarifications, unchanged
- Claude `test_resume_load_receipts_do_not_enter_current_attempt` is not in this batch's scope.
- The OpenCode config literal test still leaves tools, share and autoupdate unasserted. That remains a possible narrow regression gap, not a demonstrated defect.

## Gaps
- **Finding 233:** byte equality for all eight cases is not proven; I did not decode or hash six of them.
- **Owner heads:** I didn't compare owner heads to c8 byte for byte; I only grepped for markers.
- **Tests not read:** the join HTTP error paths (query/fragment → 404, the 502 mapping, body length) beyond test names, and the manual editor/save/publish error mapping in `test_skills/test_operations/test_manual.py`.
- **Execution:** nothing was run, so there was no live HTTP, Windows or provider behaviour.
- **Remaining gates:** full provider/browser/manual publication and the owner merge gates remain separate. No new model execution was performed.