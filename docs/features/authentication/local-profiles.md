# Local profile approach

Status: implementation in progress, 2026-11-07. The opt-in backend and profile UI
are implemented. Real registration, switching and session-restoration acceptance
remain unverified. PR #263 is draft; this document grants no release approval.

## Owner intent

One Windows user operates the installation. Profiles select different setups,
like profiles inside one account, rather than separate hosted web accounts.
The desired first-run experience is a simple registration/profile page. A separate
administrator procedure needs concrete justification. The owner confirmed a PIN is required when entering or switching profiles. No new credential or
GitHub registration has occurred. The manual Bootstrap path has been removed.

## Reviewed direction

Reuse upstream user identities as internal profile records, and adapt its existing
signup/login UI. With AUTO_LOGIN off and NEW_USER_IS_ACTIVE on, the dedicated profile boundary
can delegate upstream creation of an active ordinary user and default project.
Generic anonymous upstream signup remains disabled to prevent validation bypass. Do not add a second profile ownership database or replace
password hashing/token validation without demonstrated need.

Proposed flow: Create profile -> enter profile -> restore it on later launches ->
Switch profile. Connecting GitHub remains a separate explicit action. This is a
target workflow; its complete real user paths are not yet verified.

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
   startup adapter skipping superuser provisioning is the alternative. The implemented adapter uses the reserved system actor solely for upstream
   startup and profile creation, excludes it from selection and refuses its login.
   Its backend boundary passed the scoped review listed below.
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

## Implementation and evidence

The manual Bootstrap module and launcher mode have been removed. The opt-in
launcher is `tools/start_local_profiles.ps1`; the existing preview factory
continues without profile mode. Profile creation delegates to the upstream user
transaction. Exact origin/host admission protects browser entry. Unsupported
identity mutations, including the nested reset-password route, are refused.
Native password/avatar editors are hidden in profile mode. Public failures use
the shared descriptive catalogue and have a coverage regression.

The React overlay implements selection, creation, PIN confirmation, uncertain-save
handling and switching. Confirmed login starts a fresh document so upstream
session initialization restores cookies without carrying previous profile state.
The owner deferred forgotten-PIN recovery: entry stays blocked and data is preserved.

Claude approved the specification at `f3400b7` and backend at `ad30ec7` after the
nested reset-password correction. Those approvals exclude subsequent UI changes
and runtime acceptance. The final UI review attempt hit the reviewer's subscription
quota; it did not run. The same reviewer session must be resumed when available.

See [the verification ledger](verification.md) for exact source revisions,
internal checks, supporting browser captures and the remaining real user stories.
No profile or PIN has been created on behalf of the owner. Keep PR #263 draft.
