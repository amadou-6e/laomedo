# Local profile verification

This record separates reviewed source, internal checks and actual user paths.
Nothing here grants browser acceptance or permission to merge.

## Reviewed revisions

| Packet | Revision | Verdict and limits |
| --- | --- | --- |
| Canonical profile specification and Draw.io | specs `f3400b7` | Claude specification and visual APPROVE for implementation; no product UI inspected. |
| Forgotten-PIN limitation | specs `34e442a` | Owner explicitly deferred recovery; preserve data and block entry when PIN is forgotten. |
| Backend own-diff from develop `bb250135` | implementation `14d3edc` | Claude REVISE: LP-I1 exposed the nested upstream reset-password route. |
| Backend focused correction | implementation `ad30ec7` | Claude backend APPROVE; LP-I1 verified fixed, LP-I2 source trace resolved. UI, final-head live paths and owner inspection excluded. |

The same Claude reviewer session was reused at low effort, with 300-second bounded
packets. Reviewer approval is scoped to the listed source and cannot be reused as
an approval of later UI changes or browser behavior.

## Finding dispositions

- LP-R1 through LP-R7: corrected and rechecked at specs `f3400b7`.
- LP-R8: accepted owner constraint at `34e442a`, not a recovery implementation.
- LP-R9 / LP-I2: effective service registration and inherited dispatch have internal
  checks. Reviewer traced the pinned upstream JWT helpers to the guarded service.
  Real transport/browser behavior remains a separate verification requirement.
- LP-I1: all non-read operations under the upstream users tree are refused. The
  regression enumerates its actual routes, including nested reset-password.
- LP-I3: trimming precedes name length validation. Unicode composition equivalence
  is not guaranteed; case-insensitive uniqueness is the implemented rule.
- LP-I4: uncertain creation results are intentionally conservative; no automatic
  creation replay is offered.
- LP-I5: frontend source was committed at `de9b2c9`; final checks must use committed
  source so catalogue coverage is reproducible.

## Evidence limits

The earlier isolated backend started with a new database, returned an empty picker
without its internal actor, refused missing browser origin metadata and rejected
internal-account login without issuing tokens. After stopping only the task-owned
server, the same database started again. Those were pre-final-head supporting
checks with the existing frontend build. No user profile was created and no
profile/session restoration was established. An upstream telemetry-writer
WinError 87 caused its documented direct-write fallback; it remains unresolved.

The first production frontend build passed. Whole-upstream TypeScript checking
failed with 652 diagnostic lines; inspected profile/menu/route paths did not
appear in that output. No clean-baseline comparison was performed. Do not describe
that as a passed type check or proven pre-existing failures.

Final synchronized build, frontend/code/visual review and real-browser acceptance
are pending. The browser-control inventory currently reports its host unavailable.
Fixtures and API checks do not substitute for these paths.

## Required real stories

- Empty first run, registration, PIN confirmation and leading zeroes.
- Duplicate/reserved names, wrong PIN, actual rate-limit delay and retry.
- Committed creation with unconfirmed sign-in; uncertain saves without replay.
- Explicit switch and logout, failed sign-out and current-profile checking.
- Actual restoration after browser and app restart; expired login.
- Concurrent tabs/profile changes, crash recovery, human takeover and scoped cleanup.
- Existing preview compatibility and final requesting-owner inspection.

Private GitHub access additionally requires #259's revocable private-session
boundary. It is not delivered by the basic profile UI.
