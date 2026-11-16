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
