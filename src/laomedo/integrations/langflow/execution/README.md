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
