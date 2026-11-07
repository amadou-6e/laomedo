# PR250 integration and docs packet at head `357b9154`

This packet is technically approvable with fixes. The integration with the merged Skills and GitHub work kept every protection I checked, and the builder fix works. I found one lease-cleanup labelling issue (A-L-D1) and stale Claude image instructions in two setup guides (A-D-D1). This is not approval of the whole of PR250.

## What I read

- **`integration-review.diff` in full (944 lines):**
  - `host/leases/utils.py`, `integrations/langflow/viewer.py`, `tests/support/retained.py`;
  - `test_presenters.py`, `test_pull_requests/test_graph/test_feedback.py` (309 lines);
  - the new `test_host/test_leases/test_cleanup.py`, `test_settings.py`;
  - the installer, `tools/apply_langflow_skill_viewer.py`.
- **`docs-builder-review.diff` in full (404 lines).**
- **Source beyond the diffs:**
  - py-docker `containers/watch.py` (whole file, pin `49652f4`);
  - the worktree's `host/leases/utils.py:90-190`, covering `cleanup_exact` and the `supervise` caller;
  - `opencode/history/settings.py`, `claude/settings.py`, `host/runner/service.py`;
  - the existence of `codex/connection.md`, `base/agent.py`, `interface/langflow/component.py` and `experiments/exp139`.
- **Logs, summary lines only:**
  - `agents-tests-final.log`: 572 tests, OK, 2 skipped;
  - `integration-tests-sdk.log`: 43 OK;
  - `example-tests-final.log`: 8 OK;
  - `structure-tests.log`: 9 OK;
  - `installer-final.log`: overlay applied, with a "4 lines add whitespace errors" warning.
- **Not read:** `integration-resolutions.json`, `saved-skill-code-resolution.json`, the per-flow conflict and candidate JSONs, `documentation-fixes.diff`, the `prior-reviews/` files, the conservation archives, and `own-inventory.txt`.

## Your four questions

**1. Did the integration lose any accepted Skills or GitHub behaviour, or lease safety checks? Not in what I traced.**

The installer still deploys:
- the Skills feature:
  - the whole `skills/` tree as `skillFilesModal`, plus the viewer provider;
  - node controls: placeholder, hidden-control filtering in the edit and inspection panels, node description;
  - the canvas query-state test and the Monaco and icon notices;
- the binary-file preview in the viewer route (`include_binary=True`);
- the Skill editing routes, installed before the Activity routes;
- the GitHub feature:
  - the whole `github/` tree;
  - the shared error components (`ErrorExplanation.tsx`, `CopyIcon.tsx`, `nodeErrors.ts`);
  - the failed/unknown outcome patch (`github-build-outcome.patch`), applied with a check first.

Other GitHub pieces are intact:
- The GitHub inspection routes use the final `interface` clients and the `github.contract` helpers. The PR route keeps only PR error codes.
- `upstream.patch` still contains the toolbar's `prSelection`/`issueSelection` and both viewer modals (8 references).
- The PR feedback test keeps every case accepted at GitHub merge: single Agent run, refusals before the Agent, cancellation, unknown with no retry, concurrent edit, and starting from the PR. Only the module that owns `operation_value` changed path (`integrations.langflow.feedback.pr`), and the patch target follows it.

**2. Is the `late_owned` relabelling correct, and can it falsely report cleanup as verified? It never falsely verifies, but one case is mislabelled. See A-L-D1.**
- `verified` comes straight from the SDK. The SDK only verifies when the final inspection finds nothing *and* the container was removed (or the watch window is zero). So nothing is reported verified that isn't.
- The common case is right. When nothing was seen during the window and the container appears at the deadline, the SDK returns `(False, "owned")` and Laomedo relabels it `late_owned`. That matches the original behaviour, and `test_cleanup.py:577-580` checks it.

**3. Does the builder really start in a fresh process without running anything? Yes.**
- `import langflow` now runs before the LFX imports, matching the accepted GitHub builder.
- The new subprocess test runs the real CLI in a fresh interpreter. It checks for one `LaomedoCodexAgent` node and no edges.
- The builder only constructs the graph; nothing is executed. The 572-test run is now OK, not the earlier setup error.

**4. Do the restored docs match the code? Mostly. Checked against source:**
- OpenCode export budget: default 120s, allowed 45–600 via `LAOMEDO_OPENCODE_HISTORY_EXPORT_SECONDS`, 30s per export (`history/settings.py`).
- Claude image tag `2.1.310-acp0.98.0` (`claude/settings.py:5`).
- `lease_service` is required for both providers and defaults to `<state>/../lease` (`runner/service.py:55-63`).
- The new neutral paths (`agents/agents/base/agent.py`, `agents/interface/langflow/`) and the Codex connection doc exist. `experiments/exp139` exists.
- Historical OpenCode evidence stays dated, with its limits stated: one end-to-end child capture, the cause of the earlier partial capture not established, not repeatable proof.
- The Claude auth README no longer calls itself a pending draft. It moves revision-specific results to the integration record and keeps the rules on credential privacy, deadlines, the ownership receipt and the no-log policy.

The two places the docs do not match are A-D-D1 below.

## Findings

**A-L-D1 · defect · low/medium · introduced by delegating cleanup to the SDK**
- Where:
  - the SDK, `watch.py:90-98`;
  - the Laomedo relabelling, `host/leases/utils.py:113-119`;
  - the caller that writes the result, `supervise` at `:174-188`.
- Trigger: during the watch window a container was seen and removed, but the final inspection still finds it (recreated), or the inspection itself fails.
- Mechanism:
  - In that case the SDK returns `verified=False` with `detail="removed_after_loss"`.
  - The relabelling only changes `"owned"`, so the record says `{cleanup_verified: false, state: "removed_after_loss"}`.
  - The original Laomedo code returned `late_owned`, `late_unknown` or `late_conflict` here.
- Effect: not a safety failure, since nothing is wrongly marked verified. But the stored state says "removed" while a container may still exist, which misleads anyone reconciling it.
- Not covered by tests: `test_cleanup.py` only tests remove-then-absent.
- Fix: when `verified` is false and the detail starts with `"removed"`, write a "late" category (or re-inspect), or have the SDK return the final state in that case.

**A-D-D1 · docs defect · medium · inconsistency in the PR's docs**
- Where: `docs/getting-started.md:77,79,109` and `docker/claude/README.md:17,19`.
- These still tell you to build and run `laomedo-claude-controller:2.1.310`. The code expects `laomedo-claude-controller:2.1.310-acp0.98.0` (`claude/settings.py:5`), and the D1-restored `local-service.md` now says so.
- Someone following the quickstart builds an image under a different tag than the one the code and `local-service.md` expect.
- These two files are not in this diff. Correct them, or state that the ACP tag requires a different build recipe.

**A-T-S1 · test suggestion · low**
- Where: `test_presenters.py:198-204`.
- The guard now checks that `upstream.patch` mentions `@/modals/github/{issues,pull_requests}`. Those strings also appear in the `nodeKind` imports, so the guard would still pass if the toolbar's selection and viewer wiring were lost.
- The toolbar wiring is present today. Asserting `prSelection`, `issueSelection` and both viewer imports would make the guard enforce it.

**A-I-Q1 · question · low**
- `installer-final.log` warns "4 lines add whitespace errors". These came in with the switch to `--ignore-space-change`.
- It doesn't block anything, but which patch produces them, and should it be cleaned?

## Verdicts for this packet

- **Code: APPROVE with A-L-D1 to fix.** Fixing it doesn't change behaviour, but the stored cleanup state would no longer be misleading.
- **Docs: REVISE**, for A-D-D1. Restored D1–D5 and S1 otherwise match the source.
- **Spec: no spec change here.** The draft spec 403 dependency is still open.
- **Visual:** none in this packet. Fresh renders of Agent Activity and the provider graphs are still needed.

## Evidence limits

- **Internal tests only:** every passing test cited here is an internal check (mocked Docker calls, the fake GitHub provider, the deterministic Agent fixture). None of it is acceptance by a real provider or in a browser.
- **Installer run:** the installer run against the fresh pinned checkout comes from the log only.
- **Hosted CI at `357b9154`:** pending.

## What still needs review for PR250

These are the full-PR blockers as far as this packet can tell:

- **Inputs from this packet I didn't read:**
  - `integration-resolutions.json` and `saved-skill-code-resolution.json`, to confirm the 27 conflict resolutions and the 5 saved-JSON Skill-code restorations;
  - `documentation-fixes.diff`, if it differs from the docs part of `docs-builder-review.diff`.
- **Findings from earlier packets:** I did not read `prior-reviews/`, so I can't name open finding IDs from them with confidence. They should be checked against this head before the next packet.
- **Whole-PR coverage:**
  - a file-by-file comparison of `own-inventory.txt` against the earlier packet scopes is needed to list any remaining unreviewed Agent paths precisely;
  - the Activity frontend's modular deployment (beyond the installer lines shown) and `agents.patch` were not reviewed here.
- **Live and owner checks:** fresh renders of Activity and the provider graphs, live provider acceptance per Agent, and your inspection are still required before merge.