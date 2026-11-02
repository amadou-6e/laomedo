# Independent GitHub integration verification

The GitHub increment is independently based on `develop`
`20df788fe776fc0bc0d7576a5f0774880aa9e89d`. Its production source is
`eb3edeb4bd51d2aaacb225b0fb54e5debc37bec3`; this record changes documentation only.
Related workstreams are issues #244 (ownership), #245 (tests), #246 (examples)
and #247 (archives). The later Skill history and viewer polishing in PR #248
is excluded. Its checkout, uncommitted edits and preview remain separate.

## Checks on 2026-11-02

Windows, Python 3.12, existing shared Langflow/LFX environment, with `PYTHONPATH`
pointing at this worktree's `src` (source tests, not installed-wheel acceptance):

- `python -m unittest discover -s tests/test_github -t tests -q`:
  151 tests, six environmental skips, successful, 69.428 seconds.
- `python -m unittest discover -s tests/test_host/test_mediation -t tests -q`:
  23 tests, successful, 2.430 seconds.
- Pinned Black 26.10.1 checked `src/laomedo/github`, `tests/test_github`
  and `examples/github`: 87 files unchanged.
- `git diff --check origin/develop...HEAD`: successful.
- All 49 entries in `exp:archives/github-244/manifest.json` matched their
  declared byte counts, SHA256 hashes and original source Git blobs.
- All tracked GitHub test-bearing paths use `test_*` directories; support files
  retain descriptive names. The maintained examples have one shared builder,
  inspection/feedback instructions and one instruction Skill.

These are internal regression and preservation checks. They do not establish
new live Agent, GitHub-write or browser acceptance. Earlier actual workflow
results retain their exact source and scope in [the verification record](README.md).
No new model dispatch, remote resource edit or fixture demonstration occurred.

## Review corrections

Claude reviewed head `476f5d7` in the retained session: code/specification
APPROVE with follow-ups, visual REVISE for the degraded graph capture. It
explicitly disclosed limited rereading rather than a fresh line-by-line full-diff
review. That limitation remains recorded; approval is not owner acceptance.

The graph image is restored byte-for-byte from `e2eb20c8`, the earlier approved
PR #248 capture, with real icons and all outputs visible at 55% zoom. Its
historical source and difference from builder zoom 0.6 are explicit in README.

The sixth skip was reproduced by running
`test_bounded_runner_stops_descendant_before_late_effect` under the restricted
sandbox: **OS denied process-tree kill; result remains unverified**. This is a
safety-control coverage gap in the original run, not an ordinary passing result.
The same unchanged test passed in the permission-enabled full-suite rerun:
151 tests completed in 50.364 seconds, five skips (four Node, one directory
symlink), no failures/errors.
Four `test_interface.test_reviewed_cli.ReviewedIssueCliTests` cases originally
skipped because Node was not on PATH; all four passed separately with the
existing Node 22 executable on PATH (0.615 seconds). The other original skip
was `GitHubGitTransportTests.test_loose_object_symlink_refuses_before_provider_contact`
under the host directory-symlink restriction; it remains unverified locally. No production policy was relaxed.

## Remaining gates

Focused visual recheck of the corrected capture and final-head CI remain
pending. The earlier quota refusal was recovered; the actual verdict and its
coverage limits are recorded above. Requesting-owner validation of the final real workflow
is required before merging. Live uncertain-write fault testing remains unverified.
Deferred Agent experiments remain outside this increment; production tests do
not fetch the experiment branch. Skill polishing is not a prerequisite of this cut.
