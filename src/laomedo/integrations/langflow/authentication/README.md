# Private browser session admission

This package supplements upstream authentication with the revocable private
browser lease required by SC01 of the GitHub account-connection contract. It
does not authenticate passwords or validate upstream JWTs. Integration remains
unfinished until the upstream login, refresh and logout adapter is installed.

`models.py` defines `PrivateSession` (owner and lifetime) and
`IssuedPrivateSession` (the session plus a masked, nonserializable cookie).
`store.py` defines `PrivateSessionStore`, the durable SQLite lease authority:

- `issue` creates an unpredictable cookie and persists only its SHA-256 digest.
- `resolve` returns a live lease only for the authenticated matching owner.
- `renew` extends a live lease after upstream refresh; it cannot revive an
  expired, missing or revoked lease.
- `revoke` durably fences that browser lease; other leases remain independent.
- `revoke_browser` invalidates the exact incoming browser capability without
  requiring a still-valid access JWT, so expired-login logout remains possible.
- `is_revoked` checks a retained fence before forwarding refresh.

`adapter.py` owns `PrivateSessionAdapter`, the ASGI login/refresh/logout adapter.
It observes response headers without reading password bodies or replacing
upstream authentication. Successful login requires an outgoing access cookie
validated by the supplied upstream policy; lease expiry follows the outgoing
refresh cookie. A process-local policy lock serializes authentication responses
and logout. Refresh never mints a missing lease; known revoked leases are refused
before upstream refresh. Logout fences its incoming lease before upstream work;
failure stays unconfirmed. The adapter is not installed in the app yet.

`PrivateSessionAdapter._refresh_expiry` parses only the outgoing refresh cookie's
absolute expiry; `_cookie_headers` creates a persistent, HttpOnly, SameSite=Lax
loopback cookie or its deletion. `_refuse` emits a safe no-store failure.

`settings.py` defines `PrivateBrowserSettings`, explicit trusted origin and runtime
paths without dotenv or credential loading. `policy.py` defines
`PrivateAccessPolicy`: `verify_runtime` admits the native PIN-profile deployment;
`same_origin` checks browser request origin; `owner_from_token` delegates to the
upstream authentication service; `authorize` binds that validated profile to a
live private lease; `revalidate` repeats upstream activity and lease checks before
release. `_ordinary_profile` excludes the internal startup actor and superusers.
`PrivateBrowserContext` retains masked request credentials in process only and
serializes the safe session projection. No browser-supplied owner is admitted.

Writes serialize through SQLite transactions across store instances. Refresh
cannot overwrite a committed revocation. The adapter additionally serializes
authentication responses against logout; the store alone does not provide that
response ordering. Private route authorization and response-release rechecks
remain unfinished and must be installed before any private content is exposed.

`errors.py` contains the stable domain exception. Trusted callers provide an
absolute database path outside Git and public registry roots. The runtime owner
must additionally admit its private directory before constructing this store.
No cookie, credential or upstream token belongs in graphs, logs or settings.

Concern-owned tests cover persistence, owner/lifetime checks and concurrent
refresh/revocation. They are internal controls, not real browser acceptance.

The private cookie uses SameSite=Lax so a top-level GitHub OAuth return can
carry its initiating browser lease. Private reads still require exact same-origin
request metadata; the OAuth callback additionally requires its one-use state and
lease binding. New mutating controls require their separate CSRF proof. Cookie
SameSite alone does not authorize a read, callback or mutation.
