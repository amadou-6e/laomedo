**RECOVERY_DELTA: APPROVE.** Each restored method in the three diffs matches its exported original. A few were made stronger, and none were weakened. This approval covers the test-only recovery delta and nothing else.

## Empty bearer token (pr-229)
The test at `test_host/test_leases/test_http.py:211-225` matches the original `originals/pr-229/tests/test_lease_http_handler.py:247-258` exactly. In both, `"Bearer "` returns 200 and passes `token: ""` through to the mediator. The original HTTP layer already did this, so the port does not widen HTTP policy. Rejecting the empty token stays with the mediator/store, as before.

## Method-by-method comparison
| Delta method | Original | Result |
|---|---|---|
| Skill `test_http.py` (4 methods) + `utils.http_cases()` | pr-222 `:395-556` (the Skill rows) | Same routes, bodies, fallbacks (`source_unavailable`, `skill_operation_refused`), client projections (`source_discovery_failed`, `skill_operation_unavailable`), 401/no-dispatch/no-store checks and redaction |
| `test_registry/test_store.py:230-272` LF/CRLF | pr-220 skill records `:65-119` | Same preimage, hashes, retained bytes and patch assertions. The forbidden `SkillStoreTests()`/`setUp()` call is removed |
| GitHub `test_bindings.py` | pr-222 `:395-445` (Issue/PR rows) | Identical |
| `test_ownership.py` dispatcher | pr-231 `:75-98` | Adds `create_pr` and `unknown` and keeps `pr_node_read`. Adds `assertIs` identity checks on the payload and binding, so it is stronger |
| `test_values.py` Unicode digest and `owner/../repo` | pr-231 `:41-42, 56-67` | Identical assertions |
| `test_cli.py` | pr-231 `:100-124` | Identical. The patch target is valid because `context.py:11` imports `fetch_context` from `context_reader`, and `run_module` re-executes that import while the patch is active |
| Claude/OpenCode `test_recovery.py` (6 methods) | pr-213 `:22-122` | Identical apart from the renamed `OpenCodeAgent`. `py_docker` imports happen inside the functions (`agent.py:95`, `boundary.py:120,280`), so `patch("py_docker.Client")` works. The Docker skip conditions are kept |
| Lease/activity/Claude/OpenCode `test_records.py` (7 methods) | pr-220 host records `:643-853` | Identical. The `assert_secret_output_excluded` helper became `support/model_assertions.py` |
| `test_service.py` two cleanup-callback methods | pr-220 lease service `:37-159` | Identical. The existing `setUp`, `register` and `_result` match the original setup (`loss_seconds=0.5`, monotonic heartbeat) |
| Lease `test_http.py` (6 methods) + `collaborators.py` | pr-229 `:16-258` | Identical. The original `_close` thread-leak check is still enforced by `RunningHTTPServer` (`support/http_server.py:29-31` raises if the thread is still alive) |
| Langflow: OpenCode ACP completeness, LFX revision key, stale revision, and explicit fixture pin in `migrated_code` | pr-238 graph `:20-84`, migration `:13-41`, saved flow `:25-56` | Identical |

## Findings
- **Low** – `recovery-agent.diff:135,141`: `test_claude/test_recovery.py` imports `find_spec` and `patch` but never uses them. Lint only.
- **Low** – `recovery-agent.diff:300`: `test_opencode/test_recovery.py` imports `Mock` but never uses it. Lint only.
- **Low** – `test_registry/test_store.py:230-272`: the LF and CRLF cases now share one store, where the original built a fresh store for each. They still create separate drafts from the same base and every assertion is computed independently. Optionally, separate stores per case would restore full isolation. Not blocking.
- **Info (outside this delta)** – some original methods were not restored in these diffs. Their dispositions belong to the B4/retirement accounting, not to this approval:
  - pr-213 `test_retired_cli_paths_and_dynamic_codes_are_guarded` (`:124-137`);
  - pr-222 `test_redirect_is_refused_without_forwarding` (`:447`) and the Issue/PR rows of the unknown-failure test (`:457-479`);
  - pr-231's `MIGRATION["SYMBOL_PATHS"]`/`contract.pr_digest` alias assertions (`:57-73`).

## What I read
- **Diffs, all read in full:**
  - `recovery-shared.diff`
  - `recovery-github.diff`
  - `recovery-agent.diff`
- **Originals:**
  - pr-213 `test_provider_docker_recovery.py` (test list plus `:24-53`)
  - pr-220 `test_structured_skill_records.py:65-120`
  - pr-220 `test_structured_host_records.py:643-853`
  - pr-220 `test_lease_service.py:37-189`
  - pr-222 `test_http_handler_boundaries.py:395-556`
  - pr-229 `test_lease_http_handler.py:1-258`
  - pr-231 `test_github_ownership.py:41-124`
  - all three pr-238 langflow files
- **Source and support:**
  - `reconciliation-integration-237/src/laomedo/github/issues/context.py` (import line)
  - the `py_docker` import sites under `opencode/`
  - `agent-refactor-205/tests/support/http_server.py`
  - the `setUp`/`register` lines of `test_service.py`

I did not read `original-source-index.json`. None of the comparisons needed it.

This was a static, read-only review: I ran no tests, made no edits and took no GitHub actions. It does not approve the full feature, providers, visuals, retiring the 23 PRs, or any merge, and fixtures are not acceptance. B4 conservation is still incomplete.
