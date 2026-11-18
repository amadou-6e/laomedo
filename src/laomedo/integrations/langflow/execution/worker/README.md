# Single-job native graph worker

This package runs exactly one admitted saved-account graph job in a fresh
container, separated from the credential broker and every other job. The broker
supervises it; the worker never holds a GitHub credential.

## Layout and objects

```text
worker/
  __main__.py   container entry point (python -m laomedo.integrations.langflow.execution.worker)
  settings.py   GRAPH_WORKER_PREFIX, GRAPH_WORKER_MESSAGE_BYTES, GRAPH_WORKER_MODULE,
                GraphWorkerSettings
  models.py     GraphWorkerJob, GraphWorkerCall, GraphWorkerReply, GraphWorkerResult
  errors.py     GraphWorkerError
  channel.py    GraphWorkerChannel
  native.py     NativeGraphWorker
  container.py  DockerGraphWorker
```

## Contracts

`models.py` defines the private one-job bootstrap and bounded channel envelopes.
`GraphWorkerJob.private_payload` and `GraphWorkerCall.private_payload` deliberately
project a masked job capability only onto the private process pipe; normal model
serialization excludes it. Never store those private projections in graph
parameters, upstream job metadata, logs, browser responses or Agent workspaces.
The bootstrap carries the broker's graph digest and immutable catalog snapshot
(`GitHubCatalogSnapshot` from `graph_admission`).

`settings.py` owns the fixed framing/version limits and `GRAPH_WORKER_MODULE`,
the entry module that `DockerGraphWorker` launches and `Dockerfile.worker` must
also use. `GraphWorkerSettings` is the explicit host deployment: the worker image
digest and per-job limits inherited from `BaseDockerRuntimeSettings`.
`errors.py` defines `GraphWorkerError` (code `github_graph_runtime_unavailable`).
It never implies that a dispatched external write failed; callers must not
replay a write because the worker process or pipe was lost.

## Channel

`channel.py` owns `GraphWorkerChannel`: `install` admits only one job per process;
`for_graph` matches the actual graph run ID; `inspect` sends only an exact
job/vertex selector and existing read filters. Replies are matched to one serial
request. Framing is bounded, duplicate JSON fields refuse, and errors never echo
private input. It opens no network connection and never returns provider tokens.

## Native driver

`native.py` owns `NativeGraphWorker.run`, the private one-bootstrap entry point,
and `_execute`, the native graph driver. It validates the pinned source/digest
before parsing, asks native `Graph.from_payload` to defer custom constructors,
then validates the actual migrated payload before instantiating. It also checks
the native vertex's final constructor code parameter against the pinned source:
graph-provided field descriptors or edges must not redirect the constructor to
another value after source validation. Native message persistence and ambient
credential fallback are disabled; only terminal outputs leave the worker on its
private pipe. Worker prints never share that pipe.

## Container supervisor

`container.py` owns `DockerGraphWorker.run`: it verifies a local Docker context,
registers an independently supervised lease, inspects the actual sandbox before
sending a capability, dispatches bounded private-pipe reads and revokes authority
before cleanup. It reads run state only through `GitHubRunAuthority.run_for_job`
and `worker_remaining`. `cancel` accepts only the owning profile and revokes the
job before stopping it. Image IDs are immutable, and lease state must remain
outside repositories. The supervisor must validate the actual graph before
constructing components, enforce the real job timeout, revoke authority on every
terminal path, and prove container cleanup. This launcher is not yet connected to
browser admission or the preview; these building blocks are not OS-isolation or
live-node acceptance.
