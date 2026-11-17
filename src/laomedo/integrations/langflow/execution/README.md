# Isolated native graph execution

This capability owns one native graph job in a runtime separated from the
credential broker and every other job. It does not own profile identity, GitHub
tokens or mediation grants. Its first implementation is incomplete and is not
connected to the ordinary preview launcher.

`models.py` defines the private one-job bootstrap and bounded channel envelopes.
`GraphWorkerJob.private_payload` and `GraphWorkerCall.private_payload` deliberately
project a masked job capability only onto the private process pipe; normal model
serialization excludes it. Never store those private projections in graph
parameters, upstream job metadata, logs, browser responses or Agent workspaces.
The bootstrap carries the broker's graph digest and immutable catalog snapshot.

`channel.py` owns `GraphWorkerChannel`: `install` admits only one job per process;
`for_graph` matches the actual graph run ID; `inspect` sends only an exact
job/vertex selector and existing read filters. Replies are matched to one serial
request. Framing is bounded, duplicate JSON fields refuse, and errors never echo
private input. It opens no network connection and never returns provider tokens.

`settings.py` owns fixed framing/version limits. `errors.py` defines the stable
unavailable-runtime outcome. `worker.py` owns `NativeGraphWorker.run`, the private
one-bootstrap entry point, and `_execute`, the native graph driver. It validates
the pinned source/digest before parsing, asks native `Graph.from_payload` to
defer custom constructors, then validates the actual migrated payload before
instantiating. Native message persistence and ambient credential fallback are
disabled; only terminal outputs leave the worker on its private pipe. Worker
prints never share that pipe. The independently supervised
container launcher must validate the actual graph before constructing components,
enforce the real job timeout, revoke authority on every terminal path, and prove
container cleanup. The native runtime and browser proxy remain unintegrated;
these channel building blocks are not OS-isolation or live-node acceptance.

`container.py` owns `DockerGraphWorker.run`: it verifies a local Docker context,
registers an independently supervised lease, inspects the actual sandbox before
sending a capability, dispatches bounded private-pipe reads and revokes authority
before cleanup. `cancel` accepts only the owning profile and revokes the job
before stopping it. `GraphWorkerSettings` accepts explicit host deployment values
only; image IDs are immutable, and lease state must remain outside repositories.
This launcher is not yet connected to browser admission or the preview.

`base.py` owns `BaseDockerRuntime`, shared local-daemon control for the native
profile runtime and single-job worker. Its control methods filter client
environment, bound subprocess I/O, verify the local context and inspect/remove
only exact labelled container identities. Subclasses retain their own mount and
authority policy; shared transport never chooses an owner or creates a grant.

`profile.py` owns `DockerProfileRuntime`, the network-free operational API
container supervisor. `acquire` admits a current owner, `stop` removes only its
exact leased container, and `close` ends this broker's instances. A named local
volume is scoped to the explicit deployment UUID and owner UUID; container
cleanup never deletes persisted operational history. Volume labels, driver and
mount identity are verified, and no host directory is mounted. The native API's
loopback readiness check is not broker authentication. `NativeProfileInstance`
is an internal lifetime record; it is never parsed from browser data or returned
as authority. Browser forwarding and deployment activation remain unfinished.
`utils.py` contains the shared filesystem-admission helper for explicit host and
container settings. It refuses symlinks/reparse points and repository-owned
state without depending on Python 3.12-only path methods.

`native.py` owns `NativeProfileRuntime`, an untrusted native API application for
one profile's operational graph state. `create_app` configures only that separate
store and the native data identity; `lifespan` creates its ordinary operational
user and default folder. `current_user` resolves the container's fixed owner,
never a browser assertion. This identity has no authority in the credential broker.
The container must have no network, broker state or job capabilities; trusted
host admission and a private transport must precede every forwarded API request.
This application must never be mounted in the broker or exposed directly.
`native_cli.py` is its container-only entry point. The browser proxy, container
supervisor and normal UI launcher are not wired to it yet.
