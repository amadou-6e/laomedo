# Ten-pass cleanup review (4bf245a7 → 5acf38ce)

**Bottom line:** I found no concrete production defects in the parts I read. The three findings below are low severity: two leftover error-catalogue and test references to retired code, and one now-unreachable route branch. The two catalogue/test items are within your "remove leftovers" scope; the route branch is optional. They need only a light recheck. Implementation verdict: APPROVE for the read scope, with those items open.

## What the delta preserves

- **Raw `/events` behaviour is unchanged.** `BaseAgent.read_events` (`base/agent.py:178-232`) is a faithful move of the old handler body:
  - `status(run_id)` is still called first;
  - an unknown or missing attempt still returns `{"accepted": False, "events": []}`;
  - `attempt_identity_mismatch` is still raised;
  - the `native_start`/`otel_start` lower bounds, the closed-boundary `before` limits, telemetry limit 200, `tail` handling and the response keys are all the same.

  The handler now only parses the query. `_id` and `_read` are imported at `agent.py:42,45`, and the handler no longer reaches `_run_dir`.
- **Empty projection:** `project([])` returns `ActivityProjection.empty()`. It contains every key the route then rewrites (`usage`, `usage_by_thread`, `turns`, `usage_points`, `cost.amount`/`per_thread`/`reason`, `cost_reason`), and its unknown-usage fields carry an explicit "No activity observed." reason.
- **First snapshot during active capture:** `capture.py:119-141` writes the `activity/projection` snapshot before that page's `activity/record` rows. So once there is any normalized record, there is a snapshot, unless a provider page carries records with `projection=None`. That case raised `activity_projection_not_available` before this change as well. Native-only old databases now take the same path, which matches the user's out-of-scope decision.
- **Lost-ack port:** `test_lost_ack_lookup_never_repeats_native_start` exercises the current `HttpAgentBridge.lookup_request` twice. It checks the run ID is the same both times, the request hash matches, the task and profile are not leaked, and `turn_starts == 1`. The old trace-store binding assertions belonged to the retired bridge, so dropping them is correct.
- **Contract guards:**
  - `BaseAgent` is added to the signature contract set.
  - `agent_access_violations` has negative controls for a private member, an undeclared member and literal `getattr` through an alias.
  - It is applied to the handler and the join controller.
  - The provider-import guard allows only `.settings` imports outside `agents/agents/` and the registry.
- **Map removals:** only the keys and targets for the retired trace bridge and OpenCode auth are removed. The remaining map targets are still resolved by the existing tests.
- **Imports removed from Claude and OpenCode:** I checked these against the diff only. They are plain unused imports, not `TYPE_CHECKING` or framework hooks.

## Findings

**F-01 (low, leftover data): seven orphaned error-catalogue entries.**
- **Where:** `frontend/langflow-skill-viewer/node-error-catalog.json:1707-1777`.
- **What:** these entries still exist even though their codes were removed from `_ROUTABLE_ERRORS` and nothing in `src/` produces them any more:
  - `opencode_active_console_account_required`
  - `opencode_auth_redirect_rejected`
  - `opencode_console_models_required`
  - `opencode_console_origin_not_allowed`
  - `opencode_model_endpoint_not_allowed`
  - `opencode_model_sdk_not_allowed`
  - `opencode_real_credential_required`
- **Why it matters:** they are user-facing explanations for errors that can no longer occur, which is the kind of leftover this cleanup targets.
- **Fix:** remove them, unless a catalogue test requires them.

**F-02 (low, test): a stale producer name makes part of a catalogue test check nothing.**
- **Where:** `tests/test_shared/test_errors/test_catalogue.py:383`.
- **What:** it still lists `runner_trace_bridge.py` as a producer. If `producer_paths` resolves that old name to the deleted `trace_bridge.py`, the loop has nothing to check for it, so that part passes without testing anything.
- **Fix:** remove the entry.

**F-03 (optional): the route's no-snapshot truncation branch is now unreachable.**
- **Where:** `routes.py:77-103`, the `page["has_more"] and not snapshots` / "Detail limit reached" branch.
- **Why it's unreachable:** without a snapshot, any non-empty `events` now makes `project` raise before that branch runs. The only test that exercised it (`test_truncated_projection_does_not_claim_full_usage_or_cost`, which used native rows) was removed accordingly.
- **Effect:** the uncaught `ValueError` surfaces as HTTP 500, not as a stable error code. That is the same status as before for record-only pages.
- **Suggestions (optional, not a defect):** trim the dead branch, or map `activity_projection_not_available` to a stable code.

**Optional guard hardening:** the provider-import guard matches only module names that start with `laomedo.agents.agents.<provider>.`. So `from laomedo.agents.agents.codex import agent` or `import laomedo.agents.agents.codex` would not be caught. This is a false-negative limit you have already documented; it does not have to be fixed.

## Coverage

**`audit-source.diff`:**
- **Read:** lines 1–210 (docs, `legacy` deletion, `models.empty`, `projection`, `routes`, runner README), 428–537 (base README, `read_events`, Claude import removals) and 740–895 (OpenCode `executor`/`runtime`, `component` routable codes, `handler`).
- **Not read:** lines 210–428 (body of the deleted `trace_bridge.py`) and 537–740 (deleted OpenCode `auth` README, `__init__`, `transport`, `utils`). These are deletions; I verified that nothing still references them.

**`audit-tests.diff`:**
- **Read:** lines 1–80, 193–467, 984–1233 and 1321–1469.
- **Not read:** lines 80–193 (fixture JSON), 467–984 (Claude, Codex and OpenCode test edits and the `test_auth.py` deletion) and 1234–1321 (`test_graph_agent_activity`).

**Also read:** `audit-ten-passes.md`, the current `routes.py` and `capture.py` segments, and reference greps across `src`, `frontend`, `tests` and `docs`.

**Not verified:** the `exp` archives and the test or Black results; I relied on your statements.

## Verdicts

- **Implementation and docs:** APPROVE for the scope I read. F-01 and F-02 are low-severity leftover cleanup, and a light recheck of that small delta is enough. F-03 and the guard hardening are optional. The unread test hunks listed above are not covered by this verdict.
- **Visual:** not applicable; there is no UI change.
- **Acceptance:** the earlier Codex graph acceptance and the implementation approvals still apply only to their old revisions. This cleanup has no live acceptance of its own.
- **Not authorized:** merge or issue closure.