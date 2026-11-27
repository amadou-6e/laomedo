# Saved-account GitHub node runs

This package owns saved-account authority for the Issue and PR graph nodes
(#286): approval plans, admitted runs, job-only worker capabilities and the
buffered node reads they authorize. Its specification is
[specs PR427](https://github.com/amadou-6e/specs/pull/427). The bridge is not yet
wired into the native canvas.

It depends on [`../connections/`](../connections/README.md) only through
`GitHubConnectionService` public methods (`authorize_read`, `selected_repository`,
`confirm_read`, `read_access_token`, `run_generation_current`). It never reads
the connection journal, commit lock or credential helpers directly; the
structural guard in `tests/test_github/test_connections/test_boundaries.py`
enforces this. The connections package never imports this package.

## Layout and objects

```text
node_runs/
  models.py         GitHubNodeReadRequest, GitHubWorkerReadRequest, GitHubNodeReadResult,
                    GitHubNodeSelection, GitHubNodeAdmission, GitHubWorkerLease, GitHubNodeRun
  errors.py         GitHubNodeAuthorizationError
  settings.py       GITHUB_NODE_APPROVAL_SECONDS, GITHUB_NODE_PENDING_LIMIT
  authority.py      GitHubRunAuthority
  access.py         GitHubNodeAccess, GitHubNodeReadSession (browser reads)
  worker_access.py  GitHubWorkerAccess, GitHubWorkerReadSession (isolated-worker reads)
```

## Models

`GitHubNodeSelection` is the exact vertex, selected connection, repository, target
and requested operation kinds. `GitHubNodeAdmission` adds its online-verified
connection generation. Neither is a reusable credential or grant. `GitHubNodeRun`
holds an admitted job's trusted scope, exact graph digest and node admissions only
in broker memory; its scope and opaque reference are excluded from serialization.
`node_for_vertex` returns the admitted node for one native vertex, or `None`.
Normal profile history may retain results after disconnect; history is not live
GitHub authority. `GitHubWorkerLease` keeps only the SHA-256 of a worker
capability and its absolute monotonic deadline.

`GitHubNodeAuthorizationError` (code `github_node_authorization_unavailable`)
means the admission is missing, expired, stale or mismatched. It inherits
`GitHubConnectionError`, so existing connection-route failure mapping applies.
No credential lookup or alternate account follows from it.

## Run authority

`authority.py` owns `GitHubRunAuthority`. `digest_graph` fingerprints an
effective JSON graph rather than accepting a supplied digest. The native adapter
owns graph projection and selection extraction. `prepare` verifies each derived
selection online and creates an expiring, owner/lease-bound plan. `admit`
consumes that plan once, after the caller has confirmed the listed modifications,
and binds it to the exact flow, graph digest and native job. `_resolve` internally
revalidates its stored scope and current connection generation before returning
one exact node's repository authorization. It never chooses an account from
ambient authentication, mints a mediation grant, dispatches a write or accepts a
serialized run as proof.

`run_for_job` returns the admitted run bound to a native job, and
`worker_remaining` the seconds left on that job's worker lease; callers use these
instead of the authority's internal dictionaries. `validate_job_graph` compares
the actual worker graph before any vertex executes. Workers authenticate only
through `resolve_worker`; a job ID or browser plan reference never authenticates a
worker. `finish_job` releases terminal job bindings and their internal index.
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
budget or verification gate. The native adapter must supply trusted job/vertex
identities and keep references out of graph parameters, persisted job metadata
and Agent workspaces.

This is an incomplete integration, not a process-isolation claim. The owner
selected trusted catalog nodes plus a separate credential broker. Langflow must
not share the broker's OS vault/state access, and a saved-account worker must be
isolated from every other job. A same-user unrestricted subprocess is insufficient.
The worker capability must never enter shared graph parameters, upstream job
metadata, browser responses, logs, Agent workspaces or another worker. Broker
scope checks remain authoritative even if a worker supplies a different graph.

## Reads

`access.py` owns `GitHubNodeAccess`, the browser's selected-account read
capability. `read` verifies the profile, exact consented repository and current
account online, then composes the existing Issue/PR gateway with its unchanged
filtering and projection rules. Its `GitHubNodeReadSession` supplies credentials
only on a worker thread; every token lookup goes through
`GitHubConnectionService.read_access_token`, which revalidates the original scope
and connection generation on the broker loop under the commit lock. A finite read
deadline cannot reset between requests. The read adapter has no grant resolver
and cannot dispatch modify/close operations. Graph-run writes will use the run
authority and existing mediation contracts; this read path never substitutes for
them.

`worker_access.py` owns `GitHubWorkerAccess.inspect`, the broker's read-only
worker dispatcher, and `GitHubWorkerReadSession`, its per-call scope bridge.
`GitHubWorkerReadRequest` accepts only job/vertex selectors and existing read
filters and an optional read reference. Owner, account, repository, grants and
provider URLs are not worker-controlled fields. An admitted picker target must
match the runtime reference; when no picker target was admitted, read-only
references may select within that same consented repository. This never broadens
write targets or creates a write grant. The dispatcher derives its authority from
the admitted selection, reuses `GitHubNodeAccess.read`, and rechecks worker
authority before releasing a buffered result. Revocation during a read stops its
next credential lookup or response release. This path cannot prepare approval
plans or dispatch writes.
