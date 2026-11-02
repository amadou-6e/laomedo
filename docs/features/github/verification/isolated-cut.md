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

## Remaining gates

Full isolated-diff Claude review and final-head CI are pending. The retained
reviewer session last reported a quota refusal until 18:30 Europe/Berlin; no
new verdict is claimed. Requesting-owner validation of the final real workflow
is required before merging. Live uncertain-write fault testing remains unverified.
Deferred Agent experiments remain outside this increment; production tests do
not fetch the experiment branch. Skill polishing is not a prerequisite of this cut.
