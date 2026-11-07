# GitHub account connections for private Skill sources

Status: PROPOSED, NOT IMPLEMENTED. Owner: [issue #251](https://github.com/amadou-6e/laomedo/issues/251).
Baseline: develop `bb25013523e37fbb108b51638be171e879eb3883`.
This approach brief accompanies [canonical spec PR #411](https://github.com/amadou-6e/specs/pull/411)
and its editable UI proposal; implementation waits for the design review. See the
[one-time app setup design](setup.md).
It grants no credential access or repository write permission.

## Outcome and boundaries

Connect an explicitly chosen GitHub account in Laomedo, choose repository read
access, and discover/view a private Skill by its HTTPS URL. Credentials stay in
the host broker. Anonymous public URLs and admitted local folders keep working.
No ambient gh/GCM/environment credential fallback, Agent turn, repository write,
Git publishing or claim of hosted multi-user support is included.

Owner-selected first deployment: one Windows user and loopback-only local services.
The explicit local-owner/session mechanism remains a proposal. The owner corrected
the app-registration answer: no app exists; include one-time setup instructions. The
existing auto-login preview is not accepted as a private-connection user boundary.
Do not retrofit the shared source-service bearer token as user authentication.

## Existing seams inspected

- `skills/sources/repository.py`: constrained Git subprocesses and bare caches;
  inherited credentials/helpers are deliberately disabled. Preserve these guards.
- `skills/sources/service.py`: source indexes/cache use source URL identity only.
  Private sources must not enter that shared anonymous index or registry unchecked.
- `skills/interface/sources/handler.py`: authenticates a service bearer token,
  not a human; its request schema currently has no owner/connection context.
- `integrations/langflow/viewer.py`: authenticates requests but discards the
  resulting user identity before shared inspection/history reads. Source-only
  authorization would leave a viewer/history bypass.
- `host/credentials/token/connection.py`: explicit-file probe, explicitly not a
  production vault. Reusing it as production account management is rejected.
- `github/transport/rest`: run-oriented repository-bound operations. Source-read
  permission must not accidentally become a write grant.

## Options and proposed choice

| Choice | Coverage and cost | Disposition |
| --- | --- | --- |
| Reuse host gh/GCM or environment token | Small change, but silent identity and secret reuse violate #251 | Reject |
| Fine-grained personal token only | Useful explicit alternative, but omits required browser sign-in | Implement only as the second connection mode |
| GitHub App web authorization plus explicit token alternative | App/user repository intersection, browser consent and renewal; needs registered app and safe custody | Proposed |
| Device flow | Useful for a public desktop client, but changes the currently undecided UX/protocol | Do not add implicitly; compare if local app setup is unacceptable |
| Hosted OAuth broker | Avoids distributing an app secret but introduces a deployed service and remote custody | Excluded from proposed local first release |

Use a maintained OAuth client (assess Authlib's HTTPX integration) for state/PKCE
and exchange mechanics rather than hand-writing OAuth. Use `keyring` with an
explicit Windows backend, refusing null/plaintext/fallback backends. An OS keyring
is not protection against malicious processes running as the same Windows user.
No production dependency is selected until compatibility and behavior are reviewed.

GitHub's documented web exchange requires a client secret even with PKCE.
Therefore a locally operated app registration must supply its secret through the
host vault; never embed a shared developer secret in the package. The user confirmed that no registration exists; prepare setup instructions and
a reviewable registration configuration without creating it automatically. If self-registration is unacceptable,
return that deployment decision to the owner rather than silently using device flow.

## Proposed contracts to resolve before implementation

1. **Owner/session:** obtain the principal from the actual authenticated Langflow
   dependency, not request JSON. Require trusted startup with AUTO_LOGIN disabled, reject a default auto-login
   principal, and bind a non-default owner UUID explicitly. The request-local
   auth method alone is insufficient: an auto-login-issued cookie is subsequently
   classified as JWT. Reject unsupported auth modes and unknown owner/session
   contexts; do not change existing service settings automatically. Validate actual persistence,
   logout/expiry and browser restart; never claim session guarantees from cookies
   merely existing. Keep public/local paths available without private admission.
2. **Connection:** non-secret owner, verified GitHub principal, connection ID,
   monotonically advancing generation, mode, selected repositories, expiry/state.
   Tokens, refresh values, PKCE verifier and app secret never enter public models.
3. **Sign-in:** fixed registered loopback callback, S256 PKCE, unpredictable state,
   exact initiating owner/session/request binding, finite expiry and one-use
   callback. Persist pending state safely or invalidate it explicitly on restart.
   Concurrent attempts cannot replace a newer connection. No callback success
   until exchange and principal verification succeed.
4. **Read consent:** propose explicit repository-specific read consent, not a
   mediated run grant. Bind every discovery/revision/resolve/view/history read to
   owner, connection generation, repository and immutable bundle provenance.
   A connection alone does not authorize arbitrary repositories or Agent writes.
5. **Private registry authorization:** isolate private index/object cache and
   registry/journal by owner and connection generation, outside every existing
   shared registry root. This is a store access boundary, not merely caching. A shared hash can identify identical bytes but is not
   permission to read them. Gate all private inspection, history, binary and
   operation routes. Fail closed offline; no stale authorization from warm cache.
6. **Revalidation:** propose provider verification before each private user read,
   including a warm-cache view, with bounded timeout; offline access is refused.
   Local disconnect fences new reads immediately under the same lock/generation
   admission. Already delivered bytes cannot be recalled. In-flight response
   release rechecks generation. External revocation detection is measured at the
   next requested read, not asserted as an asynchronous wall-clock SLA.
7. **Renewal and crash:** serialize refresh per connection, publish replacement
   secrets/generation atomically. Ambiguous exchange/refresh crash requires
   reconnect; never reuse a possibly consumed refresh token or silently switch
   identity. Disconnect fences before removing secret material and records vault
   deletion failures without implying provider-side revocation.
8. **Explicit tokens:** assess fine-grained personal access tokens only, no classic
   tokens or borrowed installation tokens. Prefix alone is not permission proof.
   Verify principal and selected repository content reads; document which scope
   and expiry facts the actual API proves. Never claim the token is globally
   read-only merely because our adapter performs only reads. No static refresh.
9. **Private repository reads:** prefer a GitHub REST object reader after
   canonical review: matching refs, exact commits, trees and blobs provide the
   shallow head/tag snapshots used by the current source service. No requirement
   for arbitrary Git history was found: current Git clone depth is one, while
   edit lineage belongs to the local registry journal. Ref pagination, a maximum
   of 32 heads/tags, exact commit binding, recursive-tree truncation refusal,
   git object modes (refuse links/submodules), blob size/hash verification and
   existing cumulative/deadline limits must remain explicit. Provider tokens
   remain in-process HTTP authorization headers. Public Git/local readers stay
   unchanged. This is an explicit proposed private transport extension, not a
   silent replacement of Git semantics. Do not implement an askpass/broker bridge
   without a demonstrated missing API capability.
10. **Errors:** catalogue-backed Connect/Reconnect/select-repository recovery;
    ambiguous 404 says access could not be confirmed. Never infer privacy or
    existence. Preserve Source text and exact pins; refresh is read-only.

All items above are proposals, not owner-approved contract decisions. Canonical
specification and Draw.io must be reviewed before product implementation.

## Intended ownership and nomenclature

```text
src/laomedo/
  github/connections/
    README.md             connection lifecycle and method vocabulary
    models.py             ConnectionReference, ConnectionRecord, SourceReadAuthorization
    settings.py           validated non-secret connection policy
    service.py            GitHubConnectionService
    oauth.py              GitHubOAuthClient: maintained OAuth client integration
    permissions.py        GitHubRepositoryAccess: provider verification
    errors.py             documented connection-domain errors
  host/credentials/github/
    README.md             secret custody and allowed host access
    vault.py              WindowsCredentialVault: explicit OS keyring adapter
  skills/sources/
    ...                   existing bounded reader with explicit authorized context
  github/interface/connections/
    ...                   authenticated connection request/callback boundary
```

Names describe responsibility; `Base` is reserved for a demonstrated abstract
contract. Do not introduce speculative plugin registries or duplicate owner/run
models. Recurring values are Pydantic models in the owning `models.py`, with
field descriptions and safe explicit projections. Credential contents are never
serialized in public settings/models. Introduce each leaf README before its code.

## User stories and observable acceptance

| Story | Normal path | Failure/recovery and evidence required |
| --- | --- | --- |
| Browser connect | Real sign-in, verified account and repository selection | Cancel/decline/expire, replay/wrong state/session, concurrent attempts, crash; no accidental replacement |
| Explicit token | Secure intentional entry, verified account and selected repository | Unsupported/revoked/insufficient token; safe rejection and replacement without echo |
| Private Skill URL | Real authorized private URL, choices, exact pin, actual files | Wrong repository/account/org access; source preserved, no fallback or write |
| Persistence | Actual browser restart/profile restoration and broker/app restart | Expired app session, takeover and concurrent profile use constrained and tested; failed restore reconnects explicitly |
| Revocation | Disconnect/rotate fences old generations | Cold/warm cache, viewer/history/binary/operation reads, in-flight admission and refresh race; measure denial latency |
| Public/local compatibility | Anonymous public and admitted local source still work | Private failures cannot change another source's selected identity or cache |
| Diagnostics and cleanup | Descriptive errors and supported controls | No credentials in logs/exports/argv, no Agent dispatch, owned callback/service cleanup only |

Internal fixtures can test negative contracts; they cannot establish either real
connection mode, browser persistence or private-source acceptance. First real
identity/repository use needs the owner's selected connection; no token is to be
pasted into chat. Final requesting-owner workflow validation gates merge.

## Inspected external references

- [GitHub App user authorization, PKCE, client secret and access intersection](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app).
- [Callback registration and exact matching](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/about-the-user-authorization-callback-url).
- [Refresh token replacement semantics](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/refreshing-user-access-tokens).
- [Repository contents and fine-grained access](https://docs.github.com/en/rest/repos/contents#get-repository-content).
- [System keyring backends](https://keyring.readthedocs.io/en/latest/).

Checked 2026-11-07 against upstream documentation. GitHub permission metadata and Authlib compatibility still need focused
validation. The object-reader option has documented APIs but no live proof yet. No live account connection, credential copy or new runtime is claimed.

## Caller inventory and required private-store disposition

Source scan at baseline includes direct construction, inspection and transport
callers, not just the HTTP entrypoint. Ordinary trusted same-OS-user filesystem
access is outside the isolation claim; there is no protection from a malicious
local process with the user's vault/filesystem privileges.

| Existing caller | Current admission | Required disposition for private data |
| --- | --- | --- |
| Source service discover/revisions/resolve | Service bearer, source string | Add broker-verified owner/session, connection/generation and repository context; choose private store server-side |
| Viewer read including binary/images | Authenticated user discarded, root + IDs | Receive principal, authorize provenance before bytes and before releasing response; never search public root for private data |
| Viewer history/diff/compare | Same IDs sent to operations service | Route through authorized private journal; shared operations cannot reach it |
| Manual editor/save/publish | Service capability and policy, no owner | Authorize private context; prohibit publishing private-origin data into shared registry |
| Skill feedback prepare/apply | Ticket and existing edit policy | Private context must be independently admitted; never let a public ticket import private bytes |
| Graph Skill resolver | Exact public SkillReference | Carry non-secret connection reference in saved configuration; do not treat a graph-supplied owner as authority |
| Runner materialization | Shared SkillStore root and exact refs | Cannot read private root. Private Skill use needs a separately authorized materialization path; absent admission must fail descriptively, never copy into public root |
| Source and operation CLIs | Trusted registry paths plus service token | Existing defaults remain public-only; no automatic private-root selection or ambient account reuse |
| Registry origins/index and journal | Flat private host files, not authorization | Retain provenance in private store; identity/hash alone never authorizes access |

Private browsing delivery does not imply that a selected private Skill already
works in every existing Agent path. The public descriptor stays compatible;
private materialization admission must be designed explicitly and tested before
claiming that capability. No Agent model run is required to verify denial.

## Approach review record

Review at `1a887193`, actual CLI result `modelUsage` key `claude-opus-5-5`, effort low,
300-second bound: REVISE; specification INCOMPLETE, implementation/visual not
applicable. No real workflow was reviewed. Reviewer did not read all requested
instructions/callers, so its first packet is partial coverage, not full approval.

| ID | Disposition after source investigation | Remaining condition |
| --- | --- | --- |
| 251-A1 | Proposal corrected: private registry/journal isolation and caller inventory, not cache-only partition | Focused review and canonical contract |
| 251-A2 | Confirmed: current source/operation request schemas carry no owner; runner accepts exact refs from its shared store | Implement explicit private admission; no public-store import |
| 251-A3 | Pinned upstream auth inspected: auto-login can issue JWTs; reject AUTO_LOGIN deployment rather than trusting method=jwt | Owner accepts explicit local sign-in; real browser validation |
| 251-A4 | API refs/tree/blob option compared against depth-one snapshots; custom credential bridge removed from preferred approach | Canonical transport review and bounded real API proof |
| 251-A5 | Owner question pending: local app registration versus alternate deployment/protocol | Owner choice; no embedded client secret |
| 251-A6 | Source-read consent amendment is explicitly required | Reviewed canonical spec and Draw.io before implementation |
| 251-A7 | Per-request verification latency/rate-limit tradeoff retained as a proposal | Owner accepts policy; measure real read latency |

No finding is marked reviewer-verified-fixed yet. The corrected proposal and
caller coverage require focused recheck; missing real stories remain unverified.

### Focused recheck at 8c50ef07

The same low-effort reviewer inspected the corrections and required instructions.
Approach remains REVISE; specification INCOMPLETE. A1/A3/A4 proposal mechanisms
are corrected; A2 is confirmed and its implementation remains open. No runtime
or visual acceptance was established. Remaining unread handlers are recorded in
the ignored review evidence, not represented as reviewed.

- **251-A8 (open):** the existing source design's no-extra-sign-in and public/local
  transport clauses must explicitly distinguish legacy public discovery from new
  private connections. The implementation must not disable auto-login or change
  running services automatically. Under the proposed strict mode, existing public
  previews continue unchanged and private connections refuse until the owner has
  deliberately configured supported authentication. The owner has not accepted
  this prerequisite; another explicit local-owner/session design may be selected.
- **251-A9 (rejected with evidence):** the reviewer questioned model provenance.
  The actual raw CLI result contains `modelUsage.claude-opus-5-5.canonicalModel`,
  independent of the response's self-description. The record now names that exact
  evidence field; no model identity was inferred from extension/effort metadata.
  This is a provenance clarification, not a code correction or acceptance claim.
- **251-A10 (accepted clarification):** a public-only reader can serve independently
  authorized public bytes even if they happen to hash like private bytes. Private
  provenance never grants access to public callers, and a missing public pin must
  not reveal whether an inaccessible private copy exists.

Canonical authoring continues in the owner-requested separate specs worktree
on feat/410. The dirty visible specs checkout remains unchanged; no stash or
overwrite occurred. Source-read and UI requirements
remain owned by [specs #410](https://github.com/amadou-6e/specs/issues/410).

## Owner corrections and canonical checkpoint, 2026-11-07

The owner selected local Windows first and explicitly authorized a separate specs
worktree, overriding that checkout policy for this task. Then the owner corrected
the app registration answer: there is no app. Do not assume existing credentials;
prepare one-time setup without registering or modifying GitHub automatically.
The canonical draft is specs #411 at `c119de7`, with SC01-SC10 and four editable
UI pages. All pages were rendered/inspected; the validator passed with zero errors
and one unrelated existing diagram-size warning. Independent full canonical and
visual review is running; no runtime acceptance follows from a design render.
