# Private GitHub connections

Each connected GitHub account owns its own private App. `configure_app` appends
immutable owned records; `journal.apps` lists them for deliberate resumption.
`begin` requires an explicit App for a new connection and uses the saved App on
reconnect. Provisioning validates GitHub's returned owner, stores only the client
secret, and creates a lease-bound onboarding attempt before opening installation.
Only that onboarding return may automatically continue its stored authorization;
ordinary Add remains an explicit Continue action. Verified account identity must
match the App owner when known. No App is made public or deleted automatically.

This capability owns deliberate GitHub authorization and repository read consent.
`GitHubConnectionService.inspect_inventory` rechecks a browser consent attempt's
available repositories after installation. It preserves its exact owner, lease,
deadline, App version, principal, custody and connection generation; it neither
exchanges credentials nor grants access. Failure leaves the staged inventory
unchanged. The authenticated `inventory` action accepts only its request ID.
`_pending_status` projects the installation slug from that attempt's exact owned
App journal version, independently of newer deployment configuration.
It never imports host Git, gh, environment or credential-helper authentication.
When Add verifies an account already connected to this profile, `_stage` binds
the attempt to the existing connection and its current generation. Consent can
replace that connection only after Save; Cancel preserves it. `commit_connection`
also refuses a concurrent new duplicate under its SQLite transaction. Matching
uses verified numeric account identity, never a login name or another profile.
After Save, `confirm` removes retired credentials for that connection through
the existing cleanup fence. Active and live pending custody are excluded; a
deletion failure leaves the saved connection ready and cleanup retryable.

`provisioning.py` owns private App manifest registration for each GitHub account.
`GitHubAppProvisioner.begin` creates a bounded profile/lease-bound registration;
new private Apps request Contents/Metadata read and Issues/Pull requests write,
as required for saved-account nodes. GitHub's permission is an upper bound;
neither registration nor installation approves a graph mutation. Existing Apps
are never silently replaced or upgraded by this manifest change.
`complete` consumes its state before exchanging the one-use code and delegates
credential custody to `configure_app`. Unused signing material is never persisted.
`GitHubManifestClient.convert` accepts only a fixed GitHub conversion destination,
bounded response and no redirects/retries. Normal connection sign-in stays separate.
`GitHubAppProvisioningAttempt` in `models.py` holds only masked in-memory state,
trusted owner/lease and expiry. Restart abandons outstanding registrations.

`skills/` owns connection-authorized private Skill orchestration, provenance and
read routes' buffered results. Its `PrivateSkillAccess` composes the general
Skill registry and source validators without making the Skills domain import
GitHub or browser authority. The namespace is private owner/connection/repository;
no public service or Agent dispatcher constructs it. See its README for methods
and response-release guarantees.
The authenticated browser integration supplies the verified local profile and
private lease; browser JSON cannot choose an owner. This feature is in progress.

`settings.py` defines init-only `GitHubAppSettings`: an explicitly configured app
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
Browser authorization requests GitHub's account picker explicitly, including when
GitHub remembers earlier consent. Reconnect still verifies the saved numeric
principal before accepting any returned credential.
Matched sign-ins past the pending deadline report explicit expiry without an
exchange; recovery returns to the connection list for a deliberate new attempt.
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

`client.py` defines `GitHubReadClient`, a bounded GET-only fixed-origin HTTPX2
client with native TLS trust, no environment proxies, redirects or retries.
`get` admits only the provider API paths this capability uses and shares one
total operation deadline across requests. `close` releases its connections.
`GitHubRepositoryAccess.principal` obtains the actual authenticated user;
`inventory` enumerates the browser app/user installation intersection or deliberate
PAT repository candidates, refusing unfinished inventories. `verify` repeats
principal identity, numeric repository identity and Contents-read admission.
Inventory is a candidate list, not stored read consent or a write grant.

`service.py` defines `GitHubConnectionService`, one native broker's serialized
lifecycle. `configure_app` versions explicit app setup in the native vault;
`begin` creates one owner/lease-bound browser attempt; `complete` consumes its
one-use callback; `begin_token` verifies deliberately supplied token candidates.
`confirm` rechecks selected repository identities and commits explicit consent
with generation CAS. `cancel` abandons only its pending attempt, preserving ready
state. `refresh` fences uncertainty before exchange and verifies the same account;
`edit` verifies the saved credential and principal before staging repository
choices, preserving the active connection until new consent commits. It renews
an expired browser credential through the same fenced refresh path and never
starts a new sign-in automatically.
`disconnect` fences before deleting and reports unconfirmed cleanup accurately.
`authorize_read` checks current generation, consent and online access; `current`
is its synchronous response-release fence. `cleanup` handles only journaled
inactive targets, excluding live pending attempts. `status` exposes safe metadata.
`run_generation_current` additionally permits a live graph's original generation
to reach the current one only through successful refresh commits recorded by
this broker. An unrecorded transition (reconnect, consent change, revocation or
uncertain refresh) cannot be bridged by matching metadata. Restart drops both
this continuity proof and all run authority. Private buffered read responses keep
their existing exact-generation release fence.

`GitHubConnectionScope` is a trusted in-process projection supplied by the browser
adapter: verified owner, masked lease binding and a bound revalidation callback.
It is never parsed from browser JSON. The service receives the same commit lock
as the authentication response guard. Every commit revalidates under that lock;
network I/O uses the separate service lock and cannot deadlock response release.
Pending attempts remain in memory and expire; restart invalidates them while the
durable journal retains any provisional vault cleanup responsibility.

`repository.py` defines `GitHubRepositoryReader`, a nonexecuting snapshot reader
constructed only after `authorize_read`. `refs` admits at most32 complete heads
and tags from the documented complete matching-refs arrays; any advertised
unfinished pagination is refused rather than silently hiding choices. It peels
tags with a16-object visited bound. `entries` binds exact commit/tree SHA identities,
refuses recursive-tree truncation and admits only portable regular file entries.
`read_blob` checks mode, size, base64 and Git blob identity. `discover` reuses
canonical Skill name/choice validation; `revisions` collects complete validated
`PendingSkillImport` candidates without writing a shared registry. All reads share
the authorization's total deadline/byte budget. Its in-memory cache lasts for
one authorized operation; it is not offline permission or a cross-owner cache.

The journal's `revision` is an owner-scoped metadata response fence. App setup,
connection consent, refresh fencing and disconnect advance it in the same SQLite
transaction as the change. `GitHubResponseBinding` records exactly one owner
revision, connection result, pending attempt or authorized read. The native
response guard rechecks this binding while holding the same commit lock as the
service; private-session readiness alone is never private resource authority.

## Permission proof and source-location changes

GitHub documents [List branches](https://docs.github.com/en/rest/branches/branches#list-branches)
as requiring Contents read permission for GitHub App user tokens and fine-grained
PATs (checked 2026-11-10). Public resources are an explicit exception: a successful
public branch list does not prove that the credential has additional private
permissions. Each actual private source read still revalidates its selected
repository and must pass the gated object request. No globally read-only token
claim follows from this probe.

Current verification also requires the stored repository location to match its
verified numeric identity. A rename or transfer fails closed and needs deliberate
reconnection and fresh repository consent. The owner explicitly selected this
policy on 2026-11-11; consent binds both numeric identity and confirmed location.
Renewal requires reauthorization of the connection if any consented repository
cannot be verified at that location. No automatic redirect or consent migration
is permitted. Reviewer finding T1 awaits a focused contract recheck.

## Saved accounts in graph nodes (#286)

The Issue/PR node bridge is being introduced on `feat/286`; it is not yet wired
into the native canvas. Its specification is
[specs PR427](https://github.com/amadou-6e/specs/pull/427).

`models.py` owns `GitHubNodeSelection`, the exact vertex, selected connection,
repository, target and requested operation kinds, and `GitHubNodeAdmission`, its
online-verified connection generation. Neither is a reusable credential or grant.
`GitHubNodeRun` holds an admitted job's trusted scope, exact graph digest and node
admissions only in broker memory; its scope and opaque reference are excluded
from serialization. Normal profile history may retain results after disconnect;
history is not live GitHub authority.

`run_authority.py` owns `GitHubRunAuthority`. `digest_graph` fingerprints an
effective JSON graph rather than accepting a supplied digest. The native adapter
owns graph projection and selection extraction. `prepare` verifies each derived selection
online and creates an expiring, owner/lease-bound plan. `admit` consumes that plan
once, after the caller has confirmed the listed modifications, and binds it to
the exact flow, graph digest and native job. `_resolve` internally revalidates its stored
scope and current connection generation before returning one exact node's
repository authorization. It never chooses an account from ambient authentication,
mints a mediation grant, dispatches a write or accepts a serialized run as proof.
`validate_job_graph` compares the actual worker graph before any vertex executes.
Workers authenticate only through `resolve_worker`; a job ID or browser plan
reference never authenticates a worker. `finish_job` releases terminal job bindings and their internal index.
`finish` removes live authority without deleting normal owner-profile history.
`issue_worker` creates one separate masked capability for an already admitted
job. Only its hash stays in the broker; approval-plan references cannot be used
as worker credentials. `resolve_worker` authenticates that capability, derives
the account and repository from the broker's admitted vertex, and reuses the
live lease/generation checks. `revoke_worker` removes worker access independently
of history; finishing a job also revokes it. These methods are broker-internal:
no browser endpoint may issue capabilities or authenticate with a job ID alone.
An admitted run retains the trusted run scope supplied at admission rather than
the short-lived browser JWT callback used to prepare its approval plan.
`revalidate_worker` also fences worker/lease/generation at credential custody
without performing network calls or reentering the connection commit lock.
Issuance requires the actual native job's absolute monotonic deadline. The
broker refuses access at that deadline even if a terminal hook is lost and the
profile lease is still live. Rotating a worker key cannot extend the first
admitted job deadline. This is execution-timeout enforcement, not a model-turn
budget or verification gate.
The native adapter must supply trusted job/vertex identities and keep references
out of graph parameters, persisted job metadata and Agent workspaces.

This is an incomplete integration, not a process-isolation claim. The owner
selected trusted catalog nodes plus a separate credential broker. Langflow must
not share the broker's OS vault/state access, and a saved-account worker must be
isolated from every other job. A same-user unrestricted subprocess is insufficient.
The worker capability must never enter shared graph parameters, upstream job
metadata, browser responses, logs, Agent workspaces or another worker. Broker
scope checks remain authoritative even if a worker supplies a different graph.

`worker_access.py` owns `GitHubWorkerAccess.inspect`, the broker's read-only
worker dispatcher, and `GitHubWorkerReadSession`, its per-call scope bridge.
`GitHubWorkerReadRequest` accepts only job/vertex selectors and existing read
filters and an optional read reference. Owner, account, repository, grants and
provider URLs are not worker-controlled fields. An admitted picker target must
match the runtime reference; when no picker target was admitted, read-only
references may select within that same consented repository. This never broadens
write targets or creates a write grant. The dispatcher derives its authority from admitted selection,
reuses `GitHubNodeAccess.read`, and rechecks worker authority before releasing a
buffered result. Revocation during a read stops its next credential lookup or
response release. This path cannot prepare approval plans or dispatch writes.

`node_access.py` owns `GitHubNodeAccess`, the browser's selected-account read
capability. `read` verifies the profile, exact consented repository and current
account online, then composes the existing Issue/PR gateway with its unchanged
filtering and projection rules. Its `GitHubNodeReadSession` supplies credentials
only on a worker thread; every token lookup revalidates the original scope and
connection generation on the broker loop. A finite read deadline cannot reset
between requests. The read adapter has no grant resolver and cannot dispatch
modify/close operations. Graph-run writes will use the separate run authority
and existing mediation contracts; this read path never substitutes for them.
