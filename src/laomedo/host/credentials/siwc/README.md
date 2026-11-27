# Codex ChatGPT credential broker

`ChatGPTConnection` owns the private OAuth store, exchange, serialized token
rotation and exact-account revocation. `begin()` prepares an explicit login;
`finish()` validates and commits its result. `account(client_id)`,
`access_token(client_id)` and `sign_out(client_id)` always address one account.
There is no active-account pointer or implicit fallback. A failed exchange or
wrong principal leaves an existing account unchanged.

`browser.py` owns the CLI loopback interaction; `callback.py` handles that local
response. `cli.py` requires an account for status and sign-out. `utils.py` owns
private atomic writes, process locks, transport and token verification;
`settings.py` owns protocol policy and `errors.py` owns safe failures.

The Settings connection owner maps profile-owned opaque connection IDs to this
private broker. Client IDs and credential references are not graph bindings.
Authentication verification does not prove model entitlement and never needs a
model turn. Tool processes must not receive this store or its secrets.
