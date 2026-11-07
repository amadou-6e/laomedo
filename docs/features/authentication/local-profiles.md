# Local profile approach

Status: PROPOSED after owner clarification, 2026-11-07. This supersedes the
administrator-led product setup assumed by the unfinished #258 checkpoint.
No profile UI or real registration/switching acceptance is implemented yet.

## Owner intent

One Windows user operates the installation. Profiles select different setups,
like profiles inside one account, rather than separate hosted web accounts.
The desired first-run experience is a simple registration/profile page. A separate
administrator procedure needs concrete justification. The owner confirmed a PIN is required when entering or switching profiles. No new credential or
GitHub registration has occurred. The earlier manual Bootstrap handoff is on hold.

## Reviewed direction

Reuse upstream user identities as internal profile records, and adapt its existing
signup/login UI. With AUTO_LOGIN off and NEW_USER_IS_ACTIVE on, the dedicated profile boundary
can delegate upstream creation of an active ordinary user and default project.
Generic anonymous upstream signup remains disabled to prevent validation bypass. Do not add a second profile ownership database or replace
password hashing/token validation without demonstrated need.

Proposed flow: Create profile -> enter profile -> restore it on later launches ->
Switch profile. Connecting GitHub remains a separate explicit action. This is a
proposal, not a claim that a profile picker or PIN-free login already exists.

Keep profiles distinct from Windows accounts and tenant isolation. Existing
public Skill registry and activity storage are installation-shared; do not claim
all Laomedo state is profile-isolated. Private GitHub data still needs explicit
profile ownership, consent and generation checks. Retain loopback-only serving,
exact-origin/host protection, appropriate CSRF controls and OS-owned secret custody.

## Claude consultation and verified source facts

Consultation LP-1 used the existing reviewer session at low effort. Verdict:
PROCEED with upstream users as profiles, conditional on owner choices and source
investigation. This is approach advice, not implementation or user acceptance.
Reviewer read upstream users.py registration/listing and auth settings this round,
plus prior startup/auth source. It did not read the frontend or complete user
model. The following frontend/model facts were checked separately by the implementer
at upstream fec71dca901949c09ed4d63315804337cd2eb13d:

- UserCreate requires a username/password; no email or minimum PIN length is
  specified in that model. The inspected form requires name/password confirmation.
- The /signup route and login-page signup link exist. ProtectedLoginRoute redirects
  already authenticated or auto-login sessions, so adding a profile while signed
  in needs an explicit transition, not an assumption that signup is always visible.
- GET /users/ is superuser-only and returns more than profile names. A picker needs
  a narrow local profile-summary boundary; do not expose that admin response.
- Upstream user deletion forbids self-deletion and otherwise requires a superuser.
  A profile delete/reset experience therefore needs explicit design and cleanup.
- Normal startup unconditionally runs setup_superuser. This is a backend integration
  constraint, not a reason to expose an administrator workflow to the user.

## Remaining choices and minimal work

1. PIN-required is confirmed. The initial six-digit policy is proposed. Reuse
   upstream password handling; a short PIN is a convenience lock, not protection
   from the same Windows user.
2. Proposed default: GitHub connections are per profile; the GitHub App registration
   is installation-wide. Connection sharing across profiles is not selected yet.
3. Resolve startup internally. Claude recommends one reserved, automatically
   provisioned system account that is never a selectable profile. An explicit
   startup adapter skipping superuser provisioning is the alternative. Neither
   has been accepted or implemented; any privileged identity needs a clear purpose,
   reserved-name protection and reviewed lifecycle, rather than hidden complexity.
4. Reassess #259's revocable private sessions. Claude suggests upstream sessions may
   suffice under the local trust model, but removing logout/token-replay guarantees
   is a separate explicit choice. Do not drop them or close the issue implicitly.
5. Design profile creation, switching, startup/restore and recovery in the owning
   Draw.io before UI implementation. Include pending OAuth and in-flight reads.
   Forgotten-PIN recovery must not default to destructive deletion of profile data.

For #258, remove the manual Bootstrap/user-administrator workflow from the final
product and reuse existing registration. Keep useful isolation/path/environment
checks. Revise the canonical draft and issue scopes after the remaining choices;
existing issue bodies have not been changed by this consultation. Keep PR #263
in draft. All real browser creation/switching/restart and private-access stories
remain unverified.

## Design review and implementation checkpoint

Canonical spec revision `f3400b7` passed Claude's focused specification and visual
review for implementation. This is not runtime acceptance. LP-R1 through LP-R7
were corrected; LP-R8 is the owner recovery decision. LP-R9 requires tests for the
effective auth service after startup/request, environment-key refusal and all
WebSocket/SSE/MCP credential paths. The new `local_profiles` package currently owns
only safe boundary models and the auth adapter; it is not wired into serving yet.
Ten internal model/auth tests pass. Registration, startup integration, UI, actual
session persistence and real-browser acceptance remain unfinished. The old manual
bootstrap path must be removed in this PR before delivery, not retained in parallel.

## Backend implementation progress

The manual Bootstrap module and launcher mode have been removed. The opt-in
launcher is now `tools/start_local_profiles.ps1`; the existing preview factory
continues to run without profile mode. Profile creation uses a validated
registration request and the upstream user transaction. Browser entry is bound
to the configured origin. Unsupported direct identity mutations are refused.
Each public profile code has a descriptive shared-catalogue entry and an owned
coverage check. The UI still needs to consume these entries.

Real supporting backend checks on 2026-11-07: a new isolated database migrated and
started on 127.0.0.1:17867; the empty picker excluded the internal actor, absent
origin metadata was refused, and internal-actor login issued no tokens. After
an abrupt exit of only the task-owned server, the same database started again
and still returned the empty ordinary picker. These checks used the existing
frontend build, so they do not verify the new profile UI or any user profile's
session restoration. Upstream telemetry-writer startup reported WinError 87 and
fell back to direct writes; this unrelated warning is not resolved here.

The owner explicitly deferred forgotten-PIN recovery: entry to that profile is
blocked while data is preserved. LP-R8 is resolved as an accepted constraint.
