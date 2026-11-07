# GitHub account connections for private Skill sources

Status: PROPOSED, NOT IMPLEMENTED. Owner: [issue #251](https://github.com/amadou-6e/laomedo/issues/251).
Baseline: develop `bb25013523e37fbb108b51638be171e879eb3883`.
This approach brief precedes the canonical contract and editable UI design review.
It grants no credential access or repository write permission.

## Outcome and boundaries

Connect an explicitly chosen GitHub account in Laomedo, choose repository read
access, and discover/view a private Skill by its HTTPS URL. Credentials stay in
the host broker. Anonymous public URLs and admitted local folders keep working.
No ambient gh/GCM/environment credential fallback, Agent turn, repository write,
Git publishing or claim of hosted multi-user support is included.

Proposed first deployment: one Windows user, loopback-only local services and one
explicitly authenticated Laomedo owner. Owner confirmation is requested. The
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
host vault; never embed a shared developer secret in the package. The user has
been asked whether a registration exists. If self-registration is unacceptable,
return that deployment decision to the owner rather than silently using device flow.

## Proposed contracts to resolve before implementation

1. **Owner/session:** obtain the principal from the actual authenticated Langflow
   dependency, not request JSON. Require an explicitly signed-in session and a
   trusted one-owner deployment binding; reject auto-login-only, remote or
   unrecognized-owner private connection requests. Validate actual persistence,
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
5. **Cache:** isolate private index/object cache and registry/journal by owner and
   connection generation. A shared hash can identify identical bytes but is not
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
9. **Git delivery:** assess an ephemeral loopback credential broker or constrained
   askpass bridge with one-use opaque capability, exact admitted repository and
   pipe-delivered secret. Token must not enter URL, argv, persisted Git config,
   ordinary child environment, cache or stderr. Preserve redirect, hook,
   submodule, filesystem and byte/deadline guards. This feasibility question must
   be settled before selecting the bridge; do not restore ambient helpers.
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

Checked 2026-11-07 against upstream documentation. GitHub permission metadata,
Authlib compatibility and the Git credential-delivery bridge still need focused
validation. No live account connection, credential copy or new runtime is claimed.
