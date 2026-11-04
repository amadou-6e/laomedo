**Retirement is not supported yet: all 23 PRs are HOLD.** I couldn't read either triage file in full, and in the parts I did check I found two old contracts that are still not tested in the replacements (PR 217 and PR 233). The archived history on exp@6242b02b keeps the old commits, but it doesn't show the replacements still carry those contracts, so it doesn't justify closing anything yet.

## Concrete gaps found
1. **Medium – PR 217: GitHub response admission and redaction are no longer tested.** The original `test_admission_preserves_public_errors_and_strict_internal_model` (`test-contract-review-deltas.txt:2433-2447`) checked:
   - that a bad `number`, `title` or `state` in an issue or PR response raises `issue_response_invalid` / `pr_response_invalid`;
   - that a strict `GitHubIssue` validation error does not echo the invalid value (`private-invalid-value`).

   A search of combined `tests/test_github` finds neither code (only `graphql_response_invalid` and `list_response_invalid` in `test_transport/test_rest/test_delivery.py:124,140`) and no redaction check. The companion payload/digest test is preserved with independent literals in `test_contracts/test_values.py:22-81`.
   - **Needed:** restore those admission and redaction assertions in the GitHub cut (#249).
2. **Medium – PR 233: projector output order is no longer tested.** The original `test_projectors_match_frozen_old_writer_bytes` (`test-contract-review-deltas.txt:5145-5159`) checked, for every case, the exact key order (`list(actual) == case['keys']`) and the exact JSON output of both the shared and the OpenCode projector.
   - Current `tests/test_agents/test_activity/test_envelope.py` covers object identity, omitted vs empty vs null diagnostics, nesting depth and strict metadata. It never asserts the key order or output of an actual projector run.
   - This matters because the runtime changed in a way that could alter key order without any test failing. In PR 220 (`runtime-all-contract-deltas.txt:5649`), the OpenCode projector went from a literal dict to `ActivityProjection(...).to_usage_first_payload()`, while the shared projector uses the other layout.
   - Retiring the opaque base64 manifest is fine. The key-order and literal output check should come back as small literal expectations, the same way the other record tests were restored.

## Spot checks that held up
- **PR 228 Git read admission:** it changed from a denylist of prefixes to a per-command allowlist up to `--` (`settings.py:8-16`). This is stricter; there's no loss.
- **PR 228 `GitTreeEntry` → `SkillRepositoryEntry`:** intentional and matches your stated boundary.
- **PR 220 digests:** the gateways switched from `pr_digest` to `issue_digest`, which is the same function (asserted by the `assertIs(pr_digest, issue_digest)` checks at `test_values.py:81,91`). The new `try … issue/pr_grant_unavailable` wrappers only make the hash failure path stricter.
- **PR 220 `ext_agent_host_id`:** changed from `str` to an excluded `JsonValue`. That intentionally relaxes how legacy values are read. I didn't verify a test for the query encoding it mentions.
- **PR 220 heartbeat:** now logs the failing stage before re-raising. Same behaviour otherwise.
- **PR 222/224/226 Skill clients, servers and inspection:** the deltas show only additions (manual editor actions, stricter safe error projection, `include_binary`, the asset-suffix setting). The old handler classes have no direct owner, which fits the move to `interface/`; I didn't open the new handler.
- **PR 213 Claude/Codex/OpenCode (sampled lines 1–700):**
  - The Claude telemetry and command servers moved to dedicated classes (`ClaudeTelemetryHttpServer`, `CommandHttpServer`).
  - The Claude CLI stream loop was replaced by ACP `_communicate_acp`.
  - The Codex `AppServer`, `SplitAppServer`, `preflight` and `model_catalog` bodies are now `CodexController` and `asyncio` calls.
  - All of this fits the ACP replacement you described. I did not compare the new controller's preflight against the old checks (workspace/canonical/store/auth canaries, the Git binary check, `permission_preflight_failed`), so for #213/#214 that equivalence is unverified.
- **PR 221 lease result reader:** the old tests targeted the retired test harness. Current `test_service.py` still exercises transient `PermissionError` reads (lines 100–163) and malformed leases (277), which fits the boundary you stated.

## What I did not read
- **`runtime-all-contract-deltas.txt` (6,566 lines):** I read lines 1–700, 5642–5950 and 6465–6566 (about 17%). From grep, I saw all 199 headers and the 47 entries with no direct owner (PRs 213, 222, 226 and 228).
  - **Unread:** lines 700–5642 and 5950–6465. That covers the rest of PR 213 (Codex `_execute`, split, OpenCode boundary/runner, lease client/service), all of PR 214 (`CodexController`, OpenCode projection) and PR 216 (`BaseAgent`, Claude, Codex and OpenCode agents, bridge, `GitCommandRunner`, `JoinServer`, stage adapter, work-graph launch), PR 218 (Skill operations and store), and PR 226 `SkillSources`.
  - These include exactly the risky areas you listed (`_turn_available`, timeout polling and `runner_result_pending`, lifecycle/cancel/drain), and I haven't checked any of them.
- **`test-contract-review-deltas.txt` (271 entries, of which 154 have no canonical owner):** I read lines 1–60, 2416–2448, 3130–3152 and 5145–5161, plus grep listings of the headers for PRs 217, 218, 221, 227, 230, 233 and 234.
  - **Unread:** the remaining roughly 250 test versions, including all no-owner entries for PRs 213, 214, 216, 219, 220, 222–226, 228, 229, 231, 232 and 238.
- **Not opened at all this round:**
  - `fresh-bundle-verification.json`, `formatting-commits.json`, `initial-comparison.json` (so no non-Python paths: Docker, resources, templates, CI) and the raw `pr-N.diff` files;
  - `pr-metadata.json` beyond PR 213's first entries.
- **PR 236 (canonical AGENTS policy) and PR 238 (accepted-240 cleanup):** not checked against their replacements.

## Per-PR verdicts
| PR | Verdict | Reason |
|---|---|---|
| 217 | **HOLD** | Missing admission and redaction assertions (finding 1). |
| 233 | **HOLD** | Missing projector key-order and output assertion (finding 2). |
| 213, 214, 216, 218, 219, 220, 222, 223, 224, 225, 226, 228, 229, 231, 232, 238 | **HOLD** | Their runtime and/or no-owner test entries are mostly unread. The ACP, turn-cap and timeout boundaries you stated are plausible, but I haven't verified them against source. |
| 221, 227, 230, 234 | **HOLD** | The parts I checked held up (lease reader boundary; 227 and 230 tests map to named owners; the 234 tests were reviewed earlier). The full coverage of their entries isn't confirmed. |
| 236 | **HOLD** | Not inspected. |

None qualifies as READY_TO_RETIRE_CHECKPOINT on this evidence.

**To finish:**
1. Fix the gaps in #249 (finding 1) and in the Agent/Shared activity cut (finding 2).
2. Then run the review again in sessions sized to the files, roughly 1,000 lines per call, for the unread ranges listed above and the unread test entries, especially the 154 with no owner.
3. Also read `initial-comparison.json` for the non-Python paths.

This is a static, read-only audit. I reran nothing, and nothing here approves a merge, a feature or a replacement PR.
