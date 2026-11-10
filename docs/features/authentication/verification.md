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

At source `2041515b`, 37 internal Python authentication tests and five affected
frontend tests pass. These are regression checks, not real profile acceptance.
The complete TypeScript check fails in both the exact pre-profile overlay baseline
and current overlay with the same 652 diagnostic lines; their output is identical.
There are no new diagnostics, but the whole-project type check is still failing.
The tracked installer applied to fresh pinned upstream sources produces the same
14 selected native/profile files as the derived frontend workspace.

The production frontend build passed at `3be213b`. Public, empty-context headless
Edge captures at that revision show the actual picker and creation page, including
a complete 500x750 creation form. They do not establish submitted creation or
session behavior. Edge's requested 390px capture actually used a 492px CSS viewport,
so it is not evidence of 390px responsiveness. Revision `2041515b` hides unsupported native password/avatar editors; its
synchronized Vite production build passed in 3m32s. This does not verify those
authenticated settings in a browser.
Browser-control host access is unavailable; only the previously authorized public
headless Edge screenshot path was used. No credentials or existing user browser
profiles were copied into it.

The final UI review attempt at `3be213b` returned a subscription-quota refusal,
resetting at 22:30 Europe/Berlin on 2026-11-07. No UI verdict was produced. Preserve
and resume the same reviewer session after availability returns; later UI/spec
deltas still need review. PR #263 remains draft and unmerged.

## Required real stories

- Empty first run, registration, PIN confirmation and leading zeroes.
- Duplicate/reserved names, wrong PIN, actual rate-limit delay and retry.
- Committed creation with unconfirmed sign-in; uncertain saves without replay.
- Explicit switch and logout, failed sign-out and current-profile checking.
- Actual restoration after browser and app restart; expired login.
- Concurrent tabs/profile changes, crash recovery, human takeover and scoped cleanup.
- Existing preview compatibility and final requesting-owner inspection.
- Native community links also PATCH user opt-ins for optional click tracking.
  The readiness fix preserves those links while skipping tracking in profile
  mode (and when its capability check fails). Ordinary mode retains tracking;
  the backend still refuses every direct user mutation. A real authenticated
  click and final rendered review remain required.

Private GitHub access additionally requires #259's revocable private-session
boundary. It is not delivered by the basic profile UI.

## Readiness checkpoint, 2026-11-10

The tracking compatibility fix passes all 37 authentication tests and the clean
overlay installer against upstream `fec71dca901949c09ed4d63315804337cd2eb13d`.
Project-wide Black leaves 763 files unchanged. The system Node 20.11 cannot run
the installed Vite worker build (`crypto.hash` is unavailable); the isolated build
is being repeated with Node 22.23.3. No profile or PIN was created in this check.

Reviewer status: the new tracking fix is fully unreviewed — reviewer pending.
The earlier backend approval at `ad30ec7` does not cover this fix, later UI changes
or real browser acceptance. This checkpoint does not establish merge readiness.

The later real-browser switching check exposed a cross-tab logout race. Upstream
logout clears authentication/query stores, which can unmount the account menu
before its per-call mutation callbacks run. The source tab reached the picker,
but the other tab did not receive the intended context-change notification.
The fix puts the final broadcast/document reset in the mutation's `onSettled`
lifecycle callback, retaining upstream cleanup and failure recovery. This new
delta is fully unreviewed — reviewer pending; fresh build and two-tab recheck
remain required. The earlier scoped review at `7bfeffb0` was INCOMPLETE, with no
confirmed code defect; it did not establish actual switching acceptance.

The fresh two-tab recheck passes after the lifecycle correction: actual profile
creation/login, browser restart restoration, injected logout-network failure with
current-profile recovery, and successful switching all work. The second tab now
replaces its document and reaches the picker. Four incorrect PIN requests return
401, followed by an actual upstream 429; the UI clears the PIN, disables entry
and displays the server's 60-second delay. These use disposable QA profiles, not
the owner's PIN. The corrected production frontend builds successfully. The
full TypeScript check still reports 652 lines of existing diagnostics, with none
in the profile files; this is not a passing project-wide type check.
