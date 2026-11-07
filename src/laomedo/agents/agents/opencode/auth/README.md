# OpenCode authentication adapter

Provider-specific login selection and freshness validation live here. This code
does not become generic host storage simply because trusted host startup calls it.
`NoRedirect` is the explicit HTTP policy object; `redirect_request` is a required
urllib hook. Login data remains private and excluded from graphs and diagnostics.
`console_provider()` selects the active native Console account from its local
read-only database and validates the account's authenticated provider routing.
`IsolatedOpenCode` uses this loader by default. Trusted host composition can supply
a different loader with a dedicated runner profile; graph input cannot choose it.

The current real graph validation used an existing Go API login through that
explicit composition boundary. It did not validate the default Console account
database/sign-in path. No claim of Console OAuth readiness follows from that run.

## Current object interface inventory

This inventory names existing methods; the vocabulary above explains their
roles. Full signatures and detailed parameter contracts remain in source.

| Object | Defining module | Public/framework methods |
| --- | --- | --- |
| `NoRedirect` | `transport.py` | `redirect_request` |
