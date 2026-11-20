# Provider Settings browser adapter

`routes.py` installs Settings endpoints in the admitted local-profile runtime.
`session_lease()` requires the upstream HttpOnly `access_token_lf` browser cookie;
API-header identities cannot substitute for it. List/progress are inert reads.
Begin/cancel require the fixed same origin. `/auth/callback` accepts a native
top-level return only with the authenticated profile, matching session digest
and one-use OAuth state, then redirects to a query-sanitized Settings URL.

`boundary.py` defines `ProviderSessionBoundary`, which fences pending attempts
before outgoing logout or profile login. The existing profile boundary remains
the outer same-origin guard. Saved connections survive local logout. The adapter
does not expose credential borrowing over the browser API.

`bindings.py` owns `ProviderGraphBindings`: only an upstream-verified native JWT
browser session matching the framework's execution user may resolve a local
selector. Anonymous, API-key, shared foreign-owner and revoked-lease paths fail
closed. `ProviderSessionBoundary._session()` verifies the cookie principal before
setting request-local context; it never takes a graph-supplied profile ID. Native
worker-thread context propagation is tested separately from real graph acceptance.

Disconnect inspection returns the affected active-run count and admission
revision. Confirmation fences the exact connection; a stale snapshot must be
reviewed again. Polling rereads status; the owning runtime finishes confirmed
cleanup in the background. Failed cleanup exposes explicit Retry cleanup.
`exports.py` defines `strip_local_bindings()` for the pinned backend's flow
normalization and upload paths; the frontend download path applies the same
policy even if a user elects to include ordinary API keys.

A successful native `/refresh` response preserves the originating lease only when both old and new access cookies independently authenticate the same profile. The boundary inspects the server-issued Set-Cookie before forwarding it; failed refresh, mixed API authentication, logout and profile changes cannot renew a lease. Aliases contain only digests and expire with the new cookie. This keeps callback receipts readable across the frontend?s mount-time token refresh without allowing another browser of the same profile to inspect them.
