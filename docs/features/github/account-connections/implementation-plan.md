# Implementation sequence: local sign-in and private GitHub Skills

Status: PROPOSED, NOT IMPLEMENTED. Scope: [#251](https://github.com/amadou-6e/laomedo/issues/251),
[canonical spec PR #411](https://github.com/amadou-6e/specs/pull/411).
This plan follows the approved draft design, not runtime acceptance. Owner asked
for detailed steps/methods and a Claude approach review before runtime changes.

## Decisions and evidence

The owner selected single-user local Windows, normal Laomedo sign-in for private
access, and no changes to the public auto-login preview. No GitHub App exists.
GitHub setup therefore includes a deliberate first registration and installation;
credentials are entered only through a secure local control, never chat or Git.

Reuse the existing Langflow login page, password verification, user database,
access/refresh cookies and active-user authentication. Do not build a second
account database or password flow. Inspected upstream revision:
`fec71dca901949c09ed4d63315804337cd2eb13d`.

| Inspected source (relative to upstream) | Established behavior / limit |
| --- | --- |
| `src/backend/base/langflow/api/v1/login.py` | Existing POST login/refresh/logout and GET session. Logout deletes cookies; it does not revoke issued JWTs. |
| `src/backend/base/langflow/services/auth/service.py`, `create_user_tokens`, `create_refresh_token` | Tokens identify user/type/expiry, with no session identity or server-side logout registry in these paths. Refresh alone does not establish a new password login. |
| `src/backend/base/langflow/services/auth/utils.py`, `OAuth2PasswordBearerCookie` | Explicit bearer header precedes the access cookie; external auth may be a fallback. Generic authenticated user alone is insufficient for the selected browser-only private boundary. |
| `src/backend/base/langflow/services/auth/context.py` | JWT method metadata exists, but an auto-login-issued cookie is later classified as JWT too. |
| `src/backend/base/langflow/__main__.py`, `superuser` | Existing hidden password prompt can bootstrap a local administrator; do not pass passwords as argv. |
| `src/backend/base/langflow/api/v1/users.py` | Authenticated administrator may create users when public signup is disabled; activation is separately controlled. |
| `src/frontend/src/controllers/API/queries/auth/use-post-logout.ts` | Normal logout calls the backend and clears shared query/stores on success. New private buffers and late responses must join that lifecycle. |
| Laomedo `src/laomedo/integrations/langflow/viewer.py` | App factory reuses upstream authentication but current shared handlers discard principal identity. Private paths must retain it and stay outside public services. |

Source inspection is supporting evidence only. No live normal-login, session
restoration, private read or credential-store behavior has been verified.

## Ordered implementation blocks and gates

### 1. Establish an isolated normal-login deployment

Use the existing native Windows Python/Uvicorn app recipe. Create task-owned app
configuration, database and signing-key state separately from the existing preview.
Bind loopback only, with explicit trusted origin; AUTO_LOGIN disabled and public
signup disabled in this new setup only. Validate the effective startup settings,
not just environment text. Persist the upstream signing key and database using
its existing mechanism, outside Git and runner mounts.

Use a separate browser profile as well. Different localhost ports do not isolate
cookies, so a different app port alone cannot protect the existing preview's
login state. Do not copy personal profiles, cookies or credentials into that profile.

Bootstrap through the existing hidden-prompt administrator CLI, then existing
administrator user management to create/activate a non-default owner. Sign in as
that owner. Bind its verified database UUID through trusted local configuration;
never infer the owner from the first connection request or browser JSON. Keep
public signup closed. Password entry/selection belongs to the user; prepare the
concrete setup first and request only necessary interactive input.

Gate: real login, incorrect-password failure, session query, refresh, logout,
expired-session recovery, browser restart/profile restoration and app restart on
the actual deployment; public preview and unrelated sessions remain untouched.
If upstream login already fails, repair only the demonstrated integration defect.
Do not replace upstream login pre-emptively.

### 2. Admit private browser sessions explicitly

Retain the upstream authenticated active-user dependency. A private request must
also match the trusted owner and native Windows/normal-login deployment, reject
auto-login, API-key-only, bearer-only requests without a private lease, and external-auth contexts, and
have a valid revocable private browser-session lease. An auth-method string or
user UUID alone does not prove an explicit login or a live private session.

Proposed minimal addition for review: a random HttpOnly private-session cookie
plus a durable server-side lease record (digest only, owner UUID, expiry and
revocation). Issue it only after successful upstream password login, through one ASGI middleware around that route. Resolve the resulting user with
upstream token validation; never reimplement password/JWT validation, consume/log
password bodies, or mint a lease from GET session/refresh/auto-login. Do not
rewrite the upstream login response. Integration failure leaves private access
unavailable and reports that separately; a successful public login is not false
private success.

Revoke the current private lease before forwarding to upstream logout. If
revocation fails, return a safe C14 error and do not call upstream logout or claim
success. On confirmed logout, explicitly delete the private lease cookie too;
private access stays refused if cookie removal or later response delivery fails.
The private dependency requires BOTH upstream authentication and the lease, with
matching owner. Expiry/revocation and current user activity are checked on every
request and again before private response release. The owner selected matching the normal Laomedo login lifetime on 2026-11-07.
The cookie persists with an explicit expiry matching the upstream refresh cookie.
A successful upstream refresh may extend an already valid lease to the newly
issued refresh expiry, using a conditional update serialized against logout.
It never creates a lease or revives a revoked, missing or expired one. Browser
and app restart restore consistent unexpired records without another login.
Old upstream JWTs therefore cannot independently reopen private access after logout.
A normal browser request may include an Authorization header; do not reject it
merely for being present. Require the upstream-validated principal to equal the
live lease owner. A mismatched header takes upstream precedence and must fail
private admission even when a different valid cookie is also present.

This is private authorization/session binding, not another account system and
not a claim that all upstream endpoints now revoke JWTs. Other browser profiles
must obtain their own explicit-login lease. Their support is unclaimed until
tested; never overwrite an unrelated lease as a convenient cleanup step.

Use a distinct cookie name, `Path=/` (so upstream logout receives it),
HttpOnly, SameSite=Lax and a host-only cookie. Secure depends on actual HTTPS; local HTTP is supported only on the
explicit loopback deployment, with its limitation documented. Apply exact Origin/Host checks to existing login/logout/refresh POSTs,
rejecting missing or mismatched Origin in this browser-only private deployment;
this preserves the upstream form and logout hook without requiring a new token.
Use token-based CSRF as well on new private mutations whose frontend we own. OAuth callback uses its separately validated state/session/PKCE
contract, rather than assuming an Origin header on a GitHub return. No arbitrary
redirect/return target. Use ASGI response-start interception before headers are sent; do not consume
request/response bodies or replace upstream route handlers. Match exact POST
`/api/v1/login`, `/api/v1/refresh` and `/api/v1/logout` paths with empty root_path
in the supported setup. Install from the Laomedo factory after upstream app
creation and before first serving; verify effective middleware order. Login
issuance requires HTTP 200 plus an outgoing access cookie validated by upstream
authentication and matching owner; 200 alone is insufficient. Refresh extends
only its existing live lease after the same validation. No token logging or
manual JWT decoding. Logout revokes its incoming lease before passing through.
All lease updates/releases recheck revocation so a late refresh cannot reopen it.
Refuse refresh carrying a known revoked lease before upstream cookie issuance.
Test the in-flight refresh/logout race and prevent a stale refresh response from
reissuing authentication cookies after logout; private admission stays refused
regardless. The concrete response-start cancellation behavior remains an explicit
middleware compatibility/implementation check, not a demonstrated capability.

If a normal upstream login survives but the private lease is missing, expired
or inconsistent, show C13 Sign in again for private access. On deliberate action,
use the existing frontend logout mutation (clearing auth stores and query
caches as well as revoking any current private lease), then open the
existing login page. Failed/unconfirmed logout stays locked with retry (C14);
never claim sign-out or redirect as though it succeeded. This exceptional
recovery does not shorten the selected normal login lifetime or disconnect GitHub.
Private-lease errors need a dedicated client handling path so upstream automatic
401/403 refresh/retry cannot loop or silently issue a replacement lease.

Gate: API keys/bearer-only/auto-login/wrong owner cannot obtain private access;
logout plus replayed old JWT cannot restore it; concurrent tabs cannot refill
private views after lock; browser/app restart restores only unexpired consistent
leases. Hashes, session secrets and CSRF material never enter logs or public models.

### 3. Add connection lifecycle and Windows vault

Create owning module READMEs/method vocabulary before their implementation. Use
Pydantic models in owning `models.py`, external policy in `settings.py`, direct
object imports, separate object/function files and shared concern-owned test setup.

| Owner | Object / methods | Responsibility |
| --- | --- | --- |
| `integrations/langflow/authentication/` | `PrivateSessionAdapter`: install; `PrivateSessionStore`: issue, resolve, revoke; `PrivateAccessPolicy`: authorize | Adapt actual upstream login/logout and construct in-process owner/session context. No public owner-assertion endpoint. |
| `github/connections/` | `GitHubConnectionService`: begin, confirm, authorize_read, reconnect, disconnect | Pending requests, multiple connections, read consent and generation fencing. |
| `github/connections/` | `GitHubOAuthClient`: begin, complete, refresh | Maintained Authlib/HTTPX OAuth mechanics, state/PKCE and fixed callback. |
| `host/credentials/github/` | `WindowsCredentialVault`: store, load, remove | Explicit native keyring backend, fail closed without fallback. |
| `github/connections/` | `GitHubRepositoryAccess`: verify | Current principal and selected repository read access. |
| `github/connections/` | `GitHubRepositoryReader`: refs, entries, read_blob | Bounded GET-only private Git object reads; no Git subprocess credential bridge. |
| `skills/` private access owner | `PrivateSkillAccess`: inspect, history, compare | Existing validation plus authorized private provenance/store namespace. Choose exact package after caller inventory; no duplicate registry model. |

Public service bearer tokens never carry private owner identity. Private broker,
reader and store stay in the authenticated app process. Start with single-process
ownership; refuse unsupported worker topology until its locking is explicitly
designed. Keep secrets separate from non-secret journal records. Pending attempts
preserve a previous ready connection until successful explicit consent commits.
Serialize refresh/disconnect; persist uncertain exchanges as reconnect-required.
Disconnect advances generation before removing secrets; removal failure remains
fenced and offers the specified retry.

Gate: internal regression tests for transaction/crash/generation boundaries and
redaction. Real native vault persistence/removal must be verified separately;
a fake vault is not acceptance.

### 4. Implement reviewed setup and connection UI

Follow the approved Draw.io C01-C12/E01-E05/H01 states. Show exact callback from
trusted origin, not a guessed port. Configure client ID/app slug locally, store
app secret in the vault, and provide an app-specific installation link. Use
Contents read-only, required Metadata read-only, no extra account permissions or
webhooks. No GitHub settings change is automatic or implied by reviewer approval.

Confirm GitHub's exact fixed-loopback callback registration before finalizing the
callback implementation (review S17). Validate supported dependency versions and
actual OAuth/keyring behavior before pinning dependencies; do not assume an
installed package proves compatibility. Redact callback query/code and all
credential-bearing traffic from access/error logs.

Implement browser authorization as default, deliberate fine-grained token entry
as the alternative. Verify identity, show accessible repositories, require explicit
read consent; verified empty is distinct from an access failure. Cancel, decline,
expiry, replay, stale callbacks and crash never replace a ready connection.
Catalogue every changed public error and route it through the shared presenter.

Gate: actual registration with owner action, secure secret entry, real browser
return and explicit token verification. Unit tests/builds/design approval cannot
replace these paths. Do not request secrets in chat.

### 5. Connect private Skill discovery, viewer and history

Keep existing public/local readers unchanged. Route explicit private connections
through authenticated GET-only refs/commit/tree/blob reads, maintaining exact pin,
32-ref completeness, bounded tag peeling, path/mode/size/hash/deadline limits and
redirect refusal. Verify principal/repository online before each private user read;
measure actual latency and rate-limit behavior. Proposed fail-closed offline
policy needs measured owner acceptance, not a fabricated performance threshold.

Private objects, source index and edit journal are owner/connection scoped and
outside public roots, source allow-roots and runner mounts. Authorize every
inspection/history/diff/compare/binary/editor path, not merely discovery. Capture
owner/session/generation and recheck before release; UI queries/buffers clear on
logout/disconnect and late responses cannot restore them. Existing source text
and immutable pins remain selected on failure. A private error never silently
falls back to another identity or anonymous source.

Gate: real private URL and selected files/history, cold/warm caches, wrong owner,
revocation/disconnect during reads, safe errors and unchanged public/local paths.
No Agent/model execution or private-to-public export is authorized by this feature.

### 6. Validate, checkpoint and hand off

Commit and push each coherent block on feat/251. Keep experiments on exp in a
separate worktree; no probes/evidence harnesses in production. Tests live under
concern-owned `test_*` directories with shared helpers, not flat prefix groupings.
Run affected regression checks, catalogue coverage, required Black checks and CI.
Request implementation review of the full substantive own-diff plus focused
rechecks for blockers. Keep canonical spec changes ahead of implementation merge.

For final acceptance, record revision/environment and every real browser story:
normal/failing login, actual browser restart/profile restoration, app restart,
expired login, human takeover, concurrent profile behavior, interrupted startup
and crash recovery; both GitHub connection modes, private reads, revoked access,
logout/disconnect, error recovery and scoped cleanup. Mark unsupported profile or
deployment behavior explicitly. Existing images/tests/reviewer verdicts do not
prove these stories. The requesting user inspects and validates the final workflow
before any browser-related merge.

## Alternatives and review question

| Alternative | Assessment |
| --- | --- |
| Existing upstream auth without an extra private lease | Least code, but observed logout only deletes cookies; material revocation/session binding is not established. Compare against acceptance before choosing it. |
| Existing upstream auth plus narrow revocable private lease | Preferred proposal: retain existing identity/password flow while closing private logout/binding gaps. Adapter coupling and persistence must justify their cost. |
| Replace Langflow auth or add another identity provider | Duplicates working identity/session mechanisms and expands scope; no demonstrated need. |
| Put private broker behind existing public service token | Cannot derive actual browser owner and weakens the selected isolation boundary; rejected in prior review. |

Reviewer question: is this sequence the smallest sufficient path from the existing
login to #251, and does the proposed private lease close a demonstrated gap without
creating an unnecessary second login system? Challenge setup/owner bootstrap,
login/logout adapter feasibility, CSRF/cookie isolation, refresh/restart semantics,
private-route completeness and scope. A plan verdict is not runtime approval.

## Source investigation and approach review ledger

Claude review at `e40abcf8`: REVISE (narrow). Existing login reuse and the lease
were justified; P1-P3 needed corrections, P4/P5 needed source evidence. No runtime
or visual acceptance. New investigation confirms: Laomedo factory adds routes
before static catch-all, upstream router composes /api + /v1, middleware can be
installed after upstream create_app before serving, native rate-limit errors use
429 and unhandled errors 500 (not login success). The default frontend API client
uses cookies, with only language/client custom headers. Nonetheless accept a
matching validated bearer principal when a live private lease also exists.
`create_user_tokens` has no iat/session claim, so an owner logout epoch cannot
be derived safely from current JWT claims; do not add a second JWT validator.

| ID | Correction / evidence | Status |
| --- | --- | --- |
| 251-P1 | Cookie Path=/, current browser lease revoked at upstream logout | Reviewer-verified fixed in plan at e84cd4dd |
| 251-P2 | Owner chose normal-login lifetime; persistent lease tracks valid refresh, no resurrection; C13/C14 exceptional recovery | Reviewer-verified fixed in plan at e84cd4dd |
| 251-P3 | Existing login/logout/refresh Origin/Host checks; token-based CSRF confined to new owned controls | Reviewer-verified fixed in plan at e84cd4dd |
| 251-P4 | Exact routes, response-start middleware, validated outgoing cookie; no body consumption; status/error/factory sources inspected | Resolved for planning at e84cd4dd; effective middleware check still required |
| 251-P5 | Require matching upstream principal plus lease, not blanket rejection of Authorization header | Reviewer-verified fixed in plan at e84cd4dd |
| 251-P6/P7 | One table/middleware/dependency, startup-only deployment checks; bootstrap preserves non-default owner | Addressed suggestions |

First focused recheck at implementation `e84cd4dd` / specs `2db2845`: Approach
PROCEED, Specification APPROVE, Visual APPROVE (new pages 8/9). P1-P5 resolved.
The reviewer read both correction diffs and token/refresh source; router/main,
API client and exact factory details remain implementer-inspected evidence rather
than independent source coverage. No runtime capability or user acceptance follows.

| Follow-up | Implementation obligation |
| --- | --- |
| 251-P8 | Verify refresh racing with logout; block known revoked leases and prevent late auth-cookie restoration without weakening private admission. |
| 251-P9 | Revocation failure returns safe error before upstream logout; confirmed logout explicitly deletes the private cookie. |
| 251-P10 | Recovery uses the existing frontend logout mutation, clearing context/query caches. |
| 251-P11 | Optional visual consistency refinement for C14; not a design blocker. |

C13's entry trigger is now owned by N20: an otherwise authenticated private
request with missing/expired/inconsistent private session opens recovery and
clears private buffers; an invalid upstream login uses normal login recovery.
P8/P9 need implementation and real logout/concurrency evidence, not another plan
review turn. No runtime change or live acceptance is claimed.
