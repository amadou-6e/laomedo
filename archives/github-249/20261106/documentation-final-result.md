# PR249 final docs packet at head `d6721aa1`: guard fix, documentation and the four final screenshots

The guard fix keeps the original protection and makes it more precise. The documentation is accurate apart from one stale record and one garbled character. The four final screenshots show correct read, outage and recovery states.

## What I read

- **`guard-fix.diff`:** read in full (23 lines).
- **`documentation.diff`:** read in full, all 19 hunks:
  - `node-contracts.md`, `host-services.md`, the GitHub `README.md`, `architecture.md`, `connection.md`;
  - Issue and PR `README.md`, `user-stories.md` and `walkthrough.md`;
  - the new `verification/README.md` and `isolated-cut.md`;
  - the Skills walkthrough path change and `examples/README.md`;
  - `examples/github/{README.md, build_flow.py, title-skill/SKILL.md, title-skill/references/pr-operation.md}`.
- **`real-recovery.json`:** read.
- **Images, all four opened:** `real-issue-offline-idle.png`, `real-pr-offline-idle.png`, `real-issue-recovered-final.png`, `real-pr-recovered-final.png`.
- **Binary images added by the docs diff, not opened:** `verification/{issue-viewer, pr-viewer, graph, grant-refusal, missing-selection}.png`. These are restored or historical PR #248 captures, labelled as such.

## Guard fix: no requirement weakened

- The old loop asserted that GitHub-produced codes contain no "operator" text. That was what forced the shared runner entries to be rewritten.
- The new version exempts only `unauthorized` and `invalid_request` from the "operator" check (`test_errors.py:57-61`). Every other GitHub code is still checked for non-empty title, description and recovery, a title different from the code, and no "operator" text.
- The domain requirement moved to where it belongs: both viewer fallback entries must have no "runner", no "operator", and must say "repeats only this read" (`:63-69`).
- The write-unknown "before authorizing another" check is unchanged.
- A new test (`:71-77`) pins the shared runner guidance, so that wording can't be lost again.

**G-D-Q1 · question · low · pre-existing at base**
- The exemption shows that GitHub *components* can emit `unauthorized` and `invalid_request` (the loop reads codes from the component AST).
- On the GitHub node, as opposed to the viewer, `NodeErrorNotice` would therefore show runner wording ("The runner connection is not authorized").
- G-F-D1 fixed this for the viewers only. Base had the same behaviour, so this is not a regression and not a blocker for this PR. It belongs to Agent/Shared, or to a later GitHub-specific service code.

## Documentation

These claims check out against source or earlier packets:
- `architecture.md`: the ownership split (clients, handlers, listeners and startup under `github/interface/`) matches the source tree approved at `9a741243` and `test_ownership`.
- `connection.md`: the CLI paths `laomedo.github.interface.{issues,pull_requests}.cli` match the migration `CLI_PATHS` and the CLI test.
- `host-services.md`: the new test paths match the renames listed in `backend.diff`, including `test_transport/test_git/test_delivery.py` and `test_host/test_mediation/test_store.py`.
- Every reference to the old `examples/github-{issue,pr}` folders now points to `examples/github/README.md` or to the archive pinned at `714db418`. The README's `#issue-inspection-controls` anchor exists.
- The Skills walkthrough path `examples/github/title-skill` exists. The Skill and its reference ask for content only, with no identity or grant fields, which matches the contract.
- The user-story additions match the viewer behaviour I approved earlier: a safe code, the copy control, and a Refresh that only reads.

**G-D-D1 · defect · low/medium · introduced**
- Where: `docs/features/github/verification/isolated-cut.md:3-5, 385-413`.
- It describes the increment as "independently based on develop `20df788`" with production source `eb3edeb4`, and lists the remaining gates as of head `476f5d7`.
- The actual PR is based on `7c72d94`, after Skills254 merged, and has moved through `9a741243` → `9d8793a2` → `f7b233be` → `d6721aa1`.
- The page is dated, but the opening sentence is in the present tense. A reader would take an earlier cut and an outdated list of open gates as the current state.
- Fix: label it as the 2026-11-02 record of that cut, or add the current base and head and point to the newer checks.

**G-D-D2 · defect · low · introduced**
- Where: `verification/README.md:299`.
- It reads "1600 ? 1100"; the "×" was lost to an encoding error. Line 255 has the correct "1600 × 1100".

**G-D-S1 · suggestion · low**
- Where: `architecture.md:73-76`.
- The separate "Issue guide" and "PR guide" links now both point to the same `examples/github/README.md`. That's fine, but section anchors would keep the distinction.

Other doc claims are labelled as historical (PR #248 at `b41fd923`) and do not claim acceptance of PR #249. That applies to `verification/README.md`, the Claude-versus-Codex note in the PR walkthrough, and the "no production test needs exp" statement, which `test_ownership` enforces.

## Rendered states and recovery (final build, all four images opened)

- **Offline, idle (Issue and PR):**
  - The copy control now shows its resting double-rectangle icon, not ✓, which settles G-V-Q1.
  - The bold title, explanation and read-only recovery text are clear, and Technical details stays collapsed.
  - Refresh is full width and visible. No text overflows, and the long recovery line wraps inside the card at 1440px.
- **Recovered (Issue and PR):**
  - These show the same live Issue #23 and PR #24, with the same titles, labels, state and head → base, and with "Updated" unchanged.
  - The new "Read" timestamps (18:20:04 and 18:20:05) are later than the earlier 17:57 captures, consistent with a fresh read.
  - The error card is gone and there is no overflow.
- **`real-recovery.json` at `d6721aa1`:** both kinds report offline, a copyable safe error, Refresh enabled, then restored with an explicit read refresh, and `graph_dispatches: []`.
- **Limits:** the JSON contains only true/false results. It does not record the copied text, the diagnostic code, or response identities. The match to the same Issue/PR comes from the screenshots.
- G-V-S1 (redundant self button, empty space below content, raw ISO timestamps) still applies. It is optional and not a blocker.

## Verdicts

- **Test change (guard fix): APPROVE.**
- **Documentation: REVISE, low**, for G-D-D1 (the stale record) and G-D-D2 (the garbled character). Ownership, CLI, link and archive claims are accurate.
- **Spec:** no change in this packet; the earlier APPROVE stands.
- **Visual: APPROVE for the read, offline and recovered viewer states shown** at the final build. This is not full UI approval.
- **Whole PR and merge: not approved.** It needs the two doc fixes and the acceptance items below.

## Remaining acceptance gaps

- **Not verified at current head:**
  - real GitHub mutation;
  - live uncertain write or lost delivery;
  - the current standalone wheel;
  - the full TypeScript baseline comparison;
  - final CI after the guard fix.
- **Skips still listed in `isolated-cut.md`:** loose-object symlink refusal is unverified locally; the process-tree kill check passed only in the rerun with permissions enabled.
- **Not done here:** your final validation of the real workflow.
- **Not read:** the five verification PNGs added by the docs diff.

Everything else changed in the PR has now been covered across packets 1 to 5, within the stated limits.