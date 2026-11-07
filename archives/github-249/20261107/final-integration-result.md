# PR249 final review at head `3786201`: outcome fix, lease tests and live evidence

The new frontend fix does what it claims: a failed or unknown GitHub operation no longer ends with a green success banner. I found no regression in this delta. The open items are one legacy-path question, two visual questions and the technical gaps listed at the end. Merging and your acceptance are separate; I am not approving either.

## What I read for this packet

- **`final-delta.diff`, in full:**
  - `buildOutcome.ts` and its test;
  - the `models.ts` type;
  - the interface README;
  - `github-build-outcome.patch`;
  - the installer hunk;
  - `tests/test_container_lease.py`.
- **Patched upstream code:**
  - `run-flow-bridge.ts:190-449`, plus the background `onFinished` at about lines 574-616;
  - `buildUtils.ts:457-530`, plus both callers of `processEndVertexEvent` (lines 646 and 758).
- **Production code under the lease tests:** `src/laomedo/host/leases/utils.py:105-137` (`cleanup_after_loss`).
- **Evidence:** `live-operations.json`, and all five images opened:
  - `live-pr-lost-ack-fixed.png`
  - `live-pr-grant-refusal-fixed.png`
  - `live-pr-read-success-fixed.png`
  - `final-feedback-graph-fit.png`
  - `live-pr-modified.png`
- **Carried forward:** coverage from my own packets 1-5 in this session (backend at `9a741243`, tests and spec, frontend, the remaining-tests packet at `f7b233be`, docs at `d6721aa1`). I did not reopen the `*-result.md` files.

## Your four questions

**1. Can earlier runs, untouched nodes or unrelated components now fail a build? No.**
- `githubBuildFailure` only looks at `LaomedoGitHubIssue` and `LaomedoGitHubPR` nodes, including the `ext:` package form. Anything else returns nothing.
- Within those nodes it only reacts to `failed` or `unknown` in the versioned GitHub result. `succeeded` and `not_requested` never count as failures (the packet-3 admission tests cover this).
- `githubRunFailure` skips nodes that did not run, and nodes whose latest result belongs to another run. It reads only the latest result, so a later success in the same run replaces an earlier failure.
- The tests at `buildOutcome.test.ts:71-86` check every one of these cases.

**2. Can a failed or unknown GitHub result still produce a green banner? No.**
- Streamed per-node results are marked invalid and set to ERROR before being stored (`run-flow-bridge.ts:229-233`).
- The streamed run-finished handler reports failure instead of success (`:433-437`). The existing guard that keeps an earlier execution error in place still runs first.
- Background completion does the same (`:605-607`).
- The legacy path returns failure before the normal valid/BUILT branch (`buildUtils.ts:474-480`).
- The live evidence agrees: the fixed lost-acknowledgement and grant-refusal screenshots show the red error card and no green banner.

**3. Is uncertainty kept, with no extra write or hidden retry? Yes.**
- The change only touches frontend store and status state. Output data is kept, as the tests at `:102` and `:111` check. Nothing new sends requests, dispatches or retries.
- In `live-operations.json`, the real PATCH request `3befb2cc…` shows 1 GitHub mutation, then 0 extra mutations when the same identity was reconciled.
- That fault was a dropped local host-to-app response. It is not a lost upstream GitHub response.

**4. Do the lease tests still check the deadline refusal? Yes.**
- `test_creation_at_watch_deadline_remains_unverified` steps through the real `cleanup_after_loss`:
  - the deadline is set at 0.01;
  - the first inspection finds nothing;
  - the clock reads 0.02, so the deadline has passed;
  - the re-inspection finds a container the run owns, so the result is `(False, "late_owned")` and `cleanup_exact` is never called.
- That is the production path at `utils.py:127-135`.
- The other changed test only pins the clock and sleep so the original 10ms race is deterministic. No production lease code changed.

## Findings

**G-O-Q1 · question · low · introduced**
- Where: the legacy path, `buildUtils.ts:474-480` together with the event loop at `:646` and `:758`.
- On the legacy path, a GitHub failure now returns `false`. The streamed path does not stop processing on that result. In the legacy loop, `false` is the same signal an invalid component produces, so it probably stops the frontend from processing the rest of the events.
- Effect: a downstream inspector, such as one wired to Operation Result, may not display on the legacy path. The contract says Operation Result "remains routable" (`langflow-node.md`).
- Nothing is lost on the server, which has already run. This is display-only and matches how upstream treats invalid components.
- Is that acceptable on the legacy path, or should it report the error but keep consuming events?

**G-V-Q2 · visual question · low/medium · upstream rendering, new evidence**
- Where: `final-feedback-graph-fit.png`, and the same graph in the grant-refusal image.
- The feedback edge from Answer to the PR's Operation input is drawn mostly behind both nodes. Only short stubs show at the two handles.
- Its one visible straight segment runs from the right edge of the PR node (about 830,505) into the Agent's Skill References handle (about 1048,545).
- So it reads as if PR connects to Skill References, which is not an edge the builder creates. `build_flow.py` creates only task→task, answer→operation and skill→skill_reference.
- The Skill node is also cut off at the bottom of the "fit" view: Task and Operation Result sit under the zoom controls.
- The wiring is correct; this is about how it reads. Moving the Agent node in the builder would make the loop visible. Your graph inspection should confirm it.

**G-V-S2 · suggestion · low · existing card or upstream**
- In `live-pr-lost-ack-fixed.png` (156% zoom), the automatic error card covers the PR node's Discovery line and outputs.
- In `live-pr-read-success-fixed.png`, upstream's green "Flow built successfully" banner and the zoom controls cover the node's Operation Result output label ("esult").
- Both are upstream overlay placement and are optional. This sits alongside G-V-S1.

## Screenshot review

- **Lost acknowledgement:**
  - The title "The PR update outcome is not confirmed" leads.
  - The recovery tells you to read the resource first, then keep the existing record, and says "do not blindly rerun".
  - The red accent, copy icon, collapsed Technical details and Dismiss all show.
  - The text wraps inside the card, with no green banner.
- **Grant refusal:**
  - The title is "This PR operation is not authorized".
  - Technical details are expanded and show only `{"code": "pr_grant_unavailable"}`.
  - The recovery says selecting a resource does not authorize an update.
  - The card stays inside the viewport.
- **Read success:** the node build time is green, PR #24 is selected with 14 matches, and the success banner is correct for a read with no operation.
- **Modified PR #25:**
  - The title reads "GitHub PR response recovery verified": draft, open, branch `refactor-249-validation-7ddff1f3` → main.
  - The Read timestamp (09:42:07) is after the Updated time (09:42:04).
  - Hierarchy matches the earlier approved viewer, with no overflow.
- **Feedback graph:** one PR node, the existing Codex Agent (gpt-6.1-sol, low, fresh) and a separate pinned `pr-feedback-title` Skill. There is no second PR node or loop node, but see G-V-Q2.
- **What the images prove:** they show the states only. Zero extra writes, reconciliation and cleanup come from the JSON records, not from the pictures.

## Verdicts

- **Implementation** (final delta, combined with packets 1-5): **APPROVE**. G-O-Q1 is open but not blocking. Earlier items are settled: G-F-D1 fixed, G-D-D1 and G-D-D2 corrected at `daf0ebd0` per your report (I did not reread them), and the rest optional or closed.
- **Specification: APPROVE.** The specs PR409 corrections are merged. The fix brings the UI in line with "no success for failed or unknown outcomes" and "unknown results are never retried". G-O-Q1 is the only possible conflict with the contract.
- **Visual: APPROVE for the states inspected:**
  - the read, offline and recovered viewers from the earlier packet;
  - automatic unknown and refusal cards;
  - read success;
  - the modified viewer.

  The feedback-graph image is held for G-V-Q2 and your inspection. This is not full UI approval.
- **Merge: not approved.** Your final graph inspection and story validation are required.

## Not read in this packet

- The five `*-result.md` packet files.
- `live-agent-result.json`, `live-readback-cleanup.json`, `live-pr-close.json`, `live-selection-stories.json`, `live-authority-refusal.json` and `ts-final-comparison.json`.
- `wheel-parity.json`, the Jest, build and installer logs, and the two fixed browser logs.
- `issue-node.md` and `node-errors.md` were not reopened.

The claims taken from these (one real Codex run on PR #25, closing Issue #26 and PR #27, readback and cleanup, revoked grants, 265 versus 265 TypeScript diagnostics, 289 wheel files, 8 hosted checks) are your reports. I have not checked them independently.

## Technical gaps that remain

- Full TypeScript is still failing on the inherited diagnostics. It is not a green typecheck.
- No live test of a lost upstream GitHub response. Only the local acknowledgement loss was tested.
- PR creation and the Agent/ACP redesign are deferred.
- No claims about external sessions or profiles.
- Two skips are still unverified locally: the loose-object symlink refusal, and the process-tree kill check, which passed only in the rerun with permissions enabled.
- The legacy display behaviour in G-O-Q1.
- Your final graph inspection and acceptance are still required, and the PR stays unmerged until then.