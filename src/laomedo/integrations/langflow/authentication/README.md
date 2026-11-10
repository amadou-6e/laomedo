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

Writes serialize through SQLite transactions across store instances. Refresh
cannot overwrite a committed revocation. The future ASGI adapter must additionally
serialize response release against logout: this store alone does not prevent an
already prepared upstream response from setting cookies late.

`errors.py` contains the stable domain exception. Trusted callers provide an
absolute database path outside Git and public registry roots. The runtime owner
must additionally admit its private directory before constructing this store.
No cookie, credential or upstream token belongs in graphs, logs or settings.

Concern-owned tests cover persistence, owner/lifetime checks and concurrent
refresh/revocation. They are internal controls, not real browser acceptance.
