# Private browser session admission

`broker.py` owns `PrivateBrokerRuntime`, the trusted process application factory.
`create_app` builds a separate FastAPI application with only explicit native login/session
routes, the current-profile projection, owned profile registration and private
GitHub/Skill controls. It never calls `langflow.main.create_app`, mounts graph
execution/component editing APIs, starts native graph recovery, or initializes
MCP servers. `lifespan` reuses native database/auth service initialization and
teardown; the existing profile and private runtimes retain their admission,
ordinary-profile auth, lease, vault ownership and exclusive process lock checks.
The native auto-login handler is not installed. Profile admission also refuses
auto-login, authentication bypass and external identity configuration at startup.
`create_app` receives explicit profile-runtime and private-browser settings;
it does not discover credentials or another runtime from the environment.

This broker application is an API-only checkpoint. The ordinary viewer rejects
private-connections startup before constructing Langflow: its in-process graph
execution cannot safely share the credential vault. The isolated native runtime,
browser proxy, static frontend and single-job worker are not yet integrated.
No graph code may execute in the
broker, and reusable credentials or private-session cookies may not be forwarded
to the untrusted runtime. Starting a second unrestricted same-user Python process
is not isolation. Existing state is not moved or rewritten by the factory.
The broker's profile database, password hashes, signing keys and lease store are
broker-only state. An untrusted Langflow runtime must have its own separate
database and may never mount or write that identity store. The proxy must derive
profile identity from broker authentication, never from a worker's user records
or JWTs. The startup regression pins the full real broker route inventory so a
future owned runtime cannot silently install a code-evaluation endpoint.

`catalog.py` owns `GitHubGraphCatalog`. `capture` copies exact code digests for
canonical entries from a trusted host catalog; neither posted labels nor posted
hashes are inputs. Classification is host-owned in `settings.py`: unknown types,
runtime flow loaders and host-Python execution components remain refused.
`effective_graph` validates all leaf nodes, including disconnected and nested
nodes, then uses native pure-data group expansion and validates the resulting
code again after proxy input overrides. The same immutable catalog snapshot
must be retained for admission and worker construction. This does not itself
establish OS isolation or authorize a GitHub operation.
`classification` resolves canonical catalog identity without trusting posted
component names or parsing extension labels.

`node_runs.py` owns `GitHubNodeRunAdmission`, the native graph projection for
saved-account approval. `executable_graph` removes only known canvas geometry;
`effective_graph` first requires the supplied trusted catalog to validate and
expand the complete graph, including disconnected leaves. `prepare` always uses
that projection and the catalog's canonical classification, never a posted name.
`prepare` extracts account, repository, picker target and write-capable input
edges from the same effective graph that will execute. It passes canonical
`GitHubNodeSelection` values to the generic host run authority rather than
accepting a browser-supplied target list. Edges use current native `data`
handle objects; obsolete string handles are not supported by this new path.
Static requests are also write-capable; earlier PR operation outcomes never
become requests. Saved-account Issue/PR components have no Agent tool interface,
so Tool Mode is refused rather than bypassing graph approval.

`PrivateGitHubRunAdmission` is minted only from an already JWT-admitted browser
context. It retains the canonical `IssuedPrivateSession` lease/cookie projection,
not that request's short-lived access JWT. Its `revalidate` delegates to
`PrivateAccessPolicy.revalidate_run`: require the current durable lease and the
same active ordinary profile from upstream's user lookup. This allows an admitted
job to outlive access-token rotation while logout, lease expiry, profile removal
or deactivation still prevents its next private request. New browser admissions
and buffered browser responses retain their existing current-JWT checks.
Normal browser lease renewal retains the same cookie/digest, so it preserves the
job's initiating lease. A new explicit login is a different admission.

`private_nodes.py` owns buffered Issue/PR discovery and inspection at the private
GitHub-node API. `private_node_read` requires the ordinary profile, live browser
lease and CSRF proof before parsing `GitHubNodeReadRequest`; it binds the returned
payload to its exact authorized connection generation before response release.
`runtime.py` composes `GitHubNodeAccess` and the existing mediation store under
the admitted private root. This route cannot start a graph or authorize a write.
The native workflow admission and graph writes remain unfinished in #286.

This package supplements upstream authentication with the revocable private
browser lease required by SC01 of the GitHub account-connection contract. It
does not authenticate passwords or validate upstream JWTs. The opt-in native
runtime installs the upstream login, refresh and logout adapter. GitHub connection
and private content integration remain unfinished.

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
failure stays unconfirmed. The opt-in runtime installs this adapter in the app.

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
response ordering. The opt-in readiness route uses private authorization and
response-release checks. Connection-specific consent and generation checks must
also be installed before any private content is exposed.

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

`boundary.py` owns `PrivateResponseBoundary`. Its `_private_path` recognizes only
the owned private API namespaces. Before a successful response starts, the guard
requires the route's `PrivateBrowserContext`, revalidates it under the shared
policy lock, and holds that lock until the response finishes. `_refuse` replaces
an unauthorized response with a safe no-store error and discards its body.
This does not authorize a connection mutation: its service must recheck session,
consent and generation before committing as well as before response release.

`runtime.py` owns opt-in `PrivateBrowserRuntime`: `configure` installs the policy,
adapters and status route before the SPA fallback; `_admit_directory` admits only
the marked private directory, disjoint from declared public roots/agent mounts;
`_claim_process` and `_release_process` hold one native Windows broker lock;
`lifespan` verifies the final upstream profile adapter before serving.
`PrivateRuntimeMarker` binds persistent private state to its exact loopback origin.
`routes.py` owns the authenticated `private_session_status` safe readiness check.
The host must declare every configured public source root and Agent mount; the
isolated profile launcher clears external bindings and declares its public registry.
Unknown external deployments are not admitted by this setup recipe.

`PrivateGitHubAdmission` projects a verified browser context into the connection
service's trusted scope, binding the exact lease digest and a host revalidation
method. `PrivateAccessPolicy.csrf` derives a private mutation proof; `mutation`
requires it plus exact browser origin. `callback` separately admits only a fixed
top-level return with a current upstream profile and live initiating lease; the
connection service still must validate and consume one-use state/PKCE.
`PrivateGitHubResponsePolicy` checks owner metadata revisions, connection results,
pending attempts and read authorization before releasing private responses.
The shared commit lock orders these checks against logout and connection changes.

`connections.py` owns the authenticated connection HTTP adapter. `connection_index`
returns only the current profile/lease's broker metadata; `connection_action`
dispatches the fixed setup/begin/token/confirm/cancel/refresh/disconnect/cleanup
actions after browser admission and CSRF verification. `_body` bounds JSON before
manual Pydantic validation, so validation errors never echo a token or app secret.
`connection_callback` admits the fixed top-level OAuth return, consumes its bound
attempt, and redirects to the fixed manager without code/state query parameters.
`connection_capability` exposes only whether this explicit private runtime exists.
No public service bearer token can call these controls as a human owner.

`private_skills.py` owns `private_skill_action`, the fixed discover/revisions/
inspect/history/compare browser adapter. It reuses admission and bounded manual
validation before invoking `PrivateSkillAccess`; the upstream authenticated user
supplies the owner. Successful replies are fully buffered JSON and carry the
exact read authorization into the existing release fence. No public dispatcher,
private editing, materialization or streaming path is added.
