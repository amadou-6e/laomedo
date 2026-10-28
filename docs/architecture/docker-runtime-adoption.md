# Docker runtime adoption

This is the migration record for Laomedo issues #196–202. Implementation is
pending the reviewed `py-docker` release; no Docker CLI path has been replaced by
this document. The implementation baseline is 735e417, which includes the current
src-layout work on top of fetched develop 6069ac9. The visible checkout is kept
unchanged. Reconcile with develop again before opening the implementation PR.

## Ownership

The general `py-docker` distribution imports as `py_docker` and uses the official
Docker SDK. Laomedo retains provider authorization, image and CLI-version pins,
mount policy, configuration hashes, credential selection/mirroring, independent
lease supervision, publication verification and descriptive error presentation.
The runtime must not acquire application credentials or decide whether a graph
operation is authorized. Database drivers are a separate package dependency.

Pin the adopted version and artifact hashes in the lockfile. Review runtime
upgrades as changes to Laomedo's container security boundary. Stage-worker imports
and the standard-library Git credential helper must remain independent of the
runtime package. Verify the installed wheel, supported Python versions, Pydantic
ranges and pinned Langflow stage before adoption.

## Migration slices

| Issue | Existing owners | Runtime surface and remaining requirement |
| --- | --- | --- |
| #196 connection/readiness | host/runner/prerequisites.py, provider environment helpers | Client and ResolvedConnection; retain installation-vs-stopped-vs-unknown distinctions and resolve one endpoint for SDK and remaining CLI calls. |
| #197 image/CLI checks | agents/runtime/runner.py, provider containers | Images.resolve plus restricted credential-free verification container; exact expected image ID and native CLI version remain Laomedo policy. |
| #198 volumes/login copy | agents/runtime/utils.py, host/credentials/claude/utils.py | Volumes inspection/creation receipts; preserve existing named-volume labels and local-only login restrictions. Unique-volume helper alone does not migrate existing fixed auth volumes. |
| #199 launch | provider/runtime launch helpers, work_graph/docker_stage.py, publication bundle stage | ContainerSpec, reserve/create/reconcile and launch readback; compare every existing launch option before switching. No implicit pulls/builds or force replacement. |
| #200 interactive protocol | agents/runtime/servers.py, provider consumers | Execution.attach binary frames and stdin; prove real agent JSON-RPC, activity, cancellation and shutdown parity. SDK socket closure is not container termination; stdin half-close is not guaranteed. |
| #201 exec/export | command workers, publication bundle/stage.py and verified/git.py | Execution.run supports bounded binary output; archive streaming and a total end-to-end deadline are not supplied by the first prerelease. Keep the current verified export until those contracts are implemented and reviewed. |
| #202 cleanup/supervision | host/leases and publication/bundle/ownership.py | Exact immutable-ID removal and receipts; preserve absent/owned/conflict/unknown results, name replacement checks, ownership locks and independent supervisor lifetime. Never prune by prefix or port. |

The first prerelease has per-request API timeouts and a separate stream deadline.
It is not a substitute for an existing total execution deadline. Closing a stream
on timeout leaves the remote outcome uncertain until inspected and reconciled.
Generic Docker volume deletion is not exposed because volumes lack immutable IDs;
Laomedo must retain its own serialized named-volume lifecycle where required.

## Evidence and adoption gates

The library has credential-free local Windows named-pipe and Unix-socket checks.
These establish library behavior only. Internal fault-injection checks establish
recovery logic, not a real daemon failure or a working agent graph. Runtime CI,
reviewed release artifacts and PyPI name/publisher acceptance precede dependency
locking; each migration then needs its own affected checks and real agent path.

All existing public error codes and actual UI recovery controls stay intact.
Explicitly cover new producer paths in the shared error catalogue guard. A Docker
SDK failure cannot turn an unknown remote outcome into absence or justify a blind
graph retry. Docker stopped, missing and runner-offline states must keep their
distinct recovery actions from the local runner recovery contract.

The SDK owns Docker HTTP transport. The separate implementation-wide HTTPX issue
#203 concerns first-party HTTP clients; it must not monkeypatch Docker SDK internals.

Do not merge Laomedo into develop until the owner reviews the real working graph
and approves. Library CI or a package reviewer verdict does not satisfy that gate.
