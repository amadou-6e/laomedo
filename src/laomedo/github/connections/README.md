# Private GitHub connections

This capability owns deliberate GitHub authorization and repository read consent.
It never imports host Git, gh, environment or credential-helper authentication.
The authenticated browser integration supplies the verified local profile and
private lease; browser JSON cannot choose an owner. This feature is in progress.

`settings.py` defines init-only `GitHubAppSettings`: an operator-entered app
identity, masked client secret and exact fixed native callback. Its
`installation_url` constructs only the configured GitHub app's installation page.
Protocol endpoints and bounds are single-owner fixed values in that module.

`models.py` defines `GitHubOAuthAttempt`, the in-memory state/PKCE material and
authorization URL, and `GitHubConnectionCredential`, the masked credential record.
`from_oauth` admits only an expiring bearer credential with a refresh lifetime;
`from_token` admits the deliberately supported fine-grained token format but does
not establish GitHub identity or repository permission. `to_vault_value` is the
explicit secret-bearing projection, used only for Windows vault custody.

`oauth.py` defines `GitHubOAuthClient`: `begin` creates unpredictable state and
S256 PKCE using Authlib; `complete` validates the exact callback and state before
exchanging its one-use code; `refresh` requires a newly rotated refresh credential.
The service, not this protocol client, must consume pending attempts and durably
fence refresh before either exchange. No automatic retry is permitted.
`GitHubOAuthTransport` permits only POST to the fixed HTTPS token endpoint,
refuses redirects and bounds response bytes. Authlib owns OAuth parsing and
client authentication; its supported HTTPX2 client owns transport with the native
certificate store. Both dependencies are pinned together; mixing HTTPX's stream
classes with Authlib's HTTPX2 client is unsupported.
This opt-in native integration requires Python 3.11 or newer (the selected
deployment uses 3.12); the core package's Python 3.10 support is unchanged.

These protocol objects alone authorize no private read, expose no HTTP route and
make no ready-connection claim. Pending owner/lease binding, journal transactions,
principal/repository verification, consent and response-generation checks must be
composed by the connection service before live credentials are accepted.

`journal.py` defines `GitHubConnectionJournal`, the private SQLite authority.
`reserve_secret` durably records an opaque provisional vault target before any
secret write. `save_app` retains immutable app configuration versions for ready
connections. `commit_connection` atomically checks owner/generation, activates a
verified replacement and retires its old credential. `begin_refresh` first fences
the current generation into reauthorization-required; an uncertain exchange stays
there after restart. `disconnect` commits revocation before any vault deletion.
`cleanup_references` lists only inactive broker-owned targets; `finish_cleanup`
records independently confirmed absence. `current` is the synchronous generation
check used while holding the browser response/commit policy lock.
`get`, `list` and `app` are owner-filtered metadata reads. They do not load secrets
or prove current GitHub access. All database values exclude credentials and codes.
