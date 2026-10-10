# Agent-native mediated commands (draft)

Issue #100 / draft PR #105. User command-surface choice: specs PR
[312](https://github.com/amadou-6e/specs/pull/312). This is implementation
guidance, not evidence of full CLI parity or production acceptance.

The opt-in Git workspace plus a trusted GitHub run grant installs command
wrappers **inside the agent container only**. Its origin is
`laomedo::OWNER/REPO`. Native Git invokes `git-remote-laomedo`; `gh` invokes
the supported syntax adapter. Neither receives the provider token or reads
the host's GitHub login. The mediator's grant remains the authority even if
the agent changes its environment or wrapper. There is no HTTPS fallback.

## Git

`git push origin HEAD:refs/heads/RUN_BRANCH` captures the matching local branch
as the fixed handoff bundle, freezes one commit-derived attempt, polls its
verification read-only, then asks to push that exact commit. One ref only;
no force, deletion, tags, or other branch. Keep the local RUN_BRANCH ref at
the outgoing commit. Repeating a confirmed/unknown push reuses its identity;
an uncertain freeze never schedules another capture automatically. A stale
handoff lock is a refusal, not proof that its operation is safe to repeat.

The host requires an absent provider branch for the first push. Later pushes
use this run's last confirmed push from the trusted mediator journal as the
provider compare-and-swap predecessor, after a staged-object fast-forward
check. The agent cannot supply that predecessor. A remote mismatch after
dispatch remains unknown and fences the branch. Local controls are not live
multi-push acceptance evidence.

A new run has no predecessor from another run. It cannot yet adopt an
already-existing provider branch for a corrective invocation; that path
still fails conservatively and can fence the branch. S10 uses an absent
run branch and cannot establish cross-run corrective-push support.

An earlier frozen stage without a confirmed push still blocks all later
captures in that run, even after a definite push rejection. A later capture
is eligible only after the host revalidates its preceding stage and matches
a confirmed same-run/same-grant push digest. Unknown writes remain fenced
before any new capture. Automatic corrective-stage recovery is not implemented.

Stale locks and a frozen/capture-uncertain journal fail closed. Do not delete
them, generate a different identity or make a new commit to bypass them:
those actions do not resolve the preceding uncertainty. Automatic capture
recovery is not implemented; use the recorded attempt for diagnosis.

`git fetch origin` uses an explicitly granted `git_fetch` read lane for
the trusted configured base branch and the run branch. New approvals may
select these reads explicitly; existing grants are not enlarged. Host
credential custody, current ref/hash checks,
isolated Git, fsck and a grant recheck precede bundle delivery. Returned
bundles are limited to 256 KiB. Downloaded object disk usage is **not** byte
bounded by that limit; large-repository acceptance remains open.

## gh

Supported forms are `gh pr view NUMBER`, `gh run list`, GET-only `gh api
repos/OWNER/REPO/...`, `gh pr create --title TITLE --body BODY --head BRANCH
--base BASE`, and `gh pr edit NUMBER --title TITLE --body BODY`.
`--body-file FILE` (or `-` for stdin) replaces `--body`; `--repo OWNER/REPO`
must match the selected repository. Output is result JSON, not native gh
table formatting. PR reads/updates are limited to bound targets.

For writes, explicitly set `LAOMEDO_EFFECT_ID` and
`LAOMEDO_RECONCILIATION_MARKER` and include that marker in the body. A stable
effect ID identifies the **exact** request, not a command that may be edited
and resent. PR edits read the bound PR first, then submit its expected
title/body/head snapshot. A concurrent human-edit race is not eliminated.

Unsupported commands/flags fail before mediation. Exit 2 is unsupported or
invalid input; exit 3 is a mediated refusal; exit 4 means unknown effect.
Do not automatically repeat an unknown write, invent another effect ID,
export a token, or use a host gh login. Full issue/API-write/extension,
pagination and native formatting coverage is not established.

## Development verification

`python -m pytest tests/test_native_commands.py` runs host Git fixture,
revocation-before-delivery, wrapper and Node adapter controls. The opt-in
`LAOMEDO_TEST_NATIVE_DOCKER=1` adds a pinned no-network Docker fixture running
literal Git/gh commands against a synthetic client. It proves protocol
wiring, not the production verifier, provider, service lifetime, or model
behavior. One-shot S10 acceptance capture still requires independent review.
