# PR249 final recheck at head `39aef3eb`: graph layout and legacy display

Both open items are settled as non-blocking limitations. The only change at this head is the Agent's position in the example builder. Code, spec and visual verdicts are APPROVE within the limits below. None of this is merge approval or your acceptance.

## G-V-Q2 (feedback edge drawing): optional display limitation, not a blocker

- **The change:** `layout.diff` moves only the Agent node in `build_flow.py` from y=80 to y=680. Nothing else in the builder changed.
- **The builder's three edges:**
  - PR Task → Agent Task
  - Agent Answer → PR Operation
  - Skill → Agent Skill References
- **What `final-feedback-graph-clear.png` shows** (61% zoom, opened):
  - Task → Task is a visible curve.
  - Skill Reference → Skill References is a visible line.
  - The feedback edge shows as stubs at Answer (about 1230,940) and at the PR's Operation input (about 650,450), plus one straight segment. That segment runs from under the PR node (about 785,583) to the Agent's left side near "Operation/fresh" (about 1025,760), where there is no handle. So it no longer looks like PR connects to Skill References.
  - All three nodes and every output label fit with margin, and the zoom controls sit clear of all nodes.
- **Why this doesn't block:** the full return curve is still partly hidden behind the nodes. That is how upstream draws backward edges, and the PR changes nothing in the renderer. The contract asks for the PR → Agent → same PR.Operation wiring, not a fully visible curve.
- **Evidence limits:** `layout-verification.json` records `edges_unchanged`, `node_count: 3` and `all_nodes_inside_viewport_with_margin`, with no execution, on runtime `3786201` with the position change. That is the capture script's own assertion; the image is the only thing I observed directly.

## G-O-Q1 (legacy path stops displaying later events): recorded limitation, not a blocker

- No contract clause requires the frontend to keep processing events after a failure:
  - "Operation Result remains routable" (`langflow-node.md`, Execution and outputs) is about graph routing on the server, which is unchanged.
  - "Failure/unknown stops Task" (`pr-node.md:38`) is satisfied.
- The failed result is still kept by the update callback, and this matches how upstream treats invalid components.
- Recorded limitation: on the legacy path, a downstream inspector may not appear after a failed or unknown GitHub result. This has not been tested in a browser on that path. The current app uses AG-UI v2, and the streamed and background completion paths are covered by tests.

## Evidence read this round

These are records written by your scripts. They support the claims; I did not observe any of it myself.

- **`live-agent-result.json`** (at `9d8c6579`):
  - one completed native run, `0d06d33d…` (thread `01a1b52a…`, 43.474s);
  - `new_agent_runs: 1`, no intercepted requests, no page errors;
  - PR #25 title observed;
  - a 60-second grant scoped to target 25.
- **`live-readback-cleanup.json`** (at `3786201`):
  - Issue #26 closed with bug and documentation labels; PR #25 draft and open with the restored title, head, base and body preserved;
  - all listed host effects confirmed, including `3befb2cc…` from the acknowledgement-loss check;
  - all test grants revoked (2 PR grants);
  - the native run's container is gone;
  - the readback is recorded as an independent GitHub GET.

  It lists 9 confirmed PR effects across that whole testing round. The record attributes these to restoration and other separate checks. Only one of them comes from a model turn.
- **`live-pr-close.json`:** PR #27 closed, effect confirmed, head and base preserved, grant revoked, read back independently.
- **`live-selection-stories.json`:** for both Issue and PR:
  - changing the repository clears labels and selection;
  - a repository outside the host's scope is refused;
  - a missing selection is shown as its own state;
  - discovery never auto-selects;
  - label changes clear the selection;
  - the all-label filter works;
  - Refresh keeps the selected identity (#23 and #24).

  Out-of-order delivery is not claimed from these observations; internal tests cover it.
- **`live-authority-refusal.json`:** `pr_grant_unavailable` with no false success banner, the normal read banner still works, copy and dismiss work, and 0 extra Agent runs or mutations.
- **`ts-final-comparison.json`:** 265 diagnostics before and after, with 264 matching after normalization. The one difference is the inherited FilesTab AGGrid error choosing `file` versus `type`; both files involved have identical hashes. Full TypeScript still fails on these inherited errors.
- **`wheel-parity.json`** (at `d6721aa1`): 289 package files match the source bytes, and 8 isolated imports load from the wheel. That covers packaging only.
- **Logs:**
  - `build-outcome-jest-final.log`: 5 suites and 67 tests pass. The leading `NativeCommandError` is PowerShell wrapping stderr output, not a test failure.
  - `outcome-clean-install.log`: `pinned_skill_viewer_overlay_applied`.
  - `final-browser-fixed.log`: a one-line summary (Refresh kept #24; refusal with 0 runs or mutations; graph captured).

## Final verdicts (technical only)

- **Code: APPROVE** at `39aef3eb`, combining packets 1-5, the final delta, and this builder-position change.
- **Spec: APPROVE.** Canonical spec fixes are merged as specs PR409. No clause makes G-O-Q1 a blocker.
- **Visual: APPROVE for the states inspected:**
  - the viewer read, offline and recovered states;
  - automatic unknown and refusal cards;
  - read success;
  - the modified viewer;
  - the cleared feedback graph.

  The optional suggestions G-V-S1 and G-V-S2 remain, along with the known limitation on the feedback edge. This is not full UI approval.

## Not verified

- **Full TypeScript:** still fails on 265 inherited diagnostics.
- **Uncertain writes:** no upstream GitHub-side uncertain effect was tested live. The only fault injected was a lost local host-to-app acknowledgement.
- **Legacy path:** downstream display after a failure (G-O-Q1) has not been browser-tested.
- **Locally unverified skips:** the loose-object symlink refusal, and the process-tree kill check (passed only in the rerun with permissions enabled).
- **Out of scope:** PR creation, the Agent/ACP redesign, and external sessions or profiles.
- **Runtime evidence vs head:** the live evidence ran at `9d8c6579` and `3786201`, not at `39aef3eb`. That delta is the Agent position only.
- **CI for `39aef3eb`:** still running.
- **Model-turn evidence:** only one real model turn backs the feedback workflow.

## Still required from you

Your final graph inspection and story validation are still required. The PR stays unmerged until then.