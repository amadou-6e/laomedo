# Phase C file mediation bridge proposal

The pinned Codex permission profile disables network access for agent
commands. The credential-free `command/exec` probe returned `DENIED`, so the
direct `node /run/laomedo/mediate.mjs` HTTP task is not eligible for a model
turn. This design keeps that permission profile unchanged. It replaces only
the agent-to-mediator transport for the bounded local Phase C route.

## Boundary and ownership

- The runner has an explicit file-bridge mode. It still requires a run-bound
  authority and independent lease, but does not mount `grant.secret`, the
  mediator URL, or the mediator instance in the agent container. The agent
  writes requests into its disposable `/draft` mount. It receives no GitHub
  provider credential, runner API token, mediator bearer, or host service
  state path. Its Codex login volume remains the separately
  approved local prototype limitation documented in the Phase C protocol.
- An independently started host service owns the mediator store, fake
  transport, lease supervisor, and file bridge. The bridge survives a kill of
  the runner process tree. The runner cannot become the sole bridge worker.
- The host computes `<configured-run-root>/<validated-run-id>/workspace` from
  an accepted lease whose run ID is a UUID. It verifies the root and workspace
  before watching them and never uses a path supplied by the agent or lease
  JSON. The host obtains the run grant from the private lease directory and
  passes every claimed request to the existing mediator validator, including
  requests claimed after revocation. The bridge does not preemptively deny
  a revoked lease, since the mediator's `grant_unavailable` result is the
  evidence of denial.
- The fake transport records a host-side request journal containing run ID,
  effect ID, operation, monotonic claim and finish times, terminal state or error code,
  and whether a fake provider call occurred. It records no bearer, raw body,
  login, or provider response. This journal, not agent-written files or stdout,
  is the authority for effect attribution.

## File protocol

1. The agent calls the direct Node client with `--request-file` for a JSON
   file it created under `/draft`, or imports its `mediate` function for the
   long-running loop. Spawning a child Node process from Codex `command/exec`
   returned `EPERM` in the no-model preflight. The client writes a bounded JSON
   request directly at the mount root as a unique `.pending` file, closes it, then atomically
   renames it to `.json`. The host claims that final entry with `os.replace`
   into a private spool on the same host volume. It retries Windows sharing
   violations only a bounded number of times. In the private spool it rejects
   reparse points, non-regular files, hard links, oversized bodies, and
   malformed JSON. It reads each claimed file once into a bounded byte buffer.
   The agent cannot choose an intermediate host path.
2. The host invokes the existing mediator once with the request's scoped
   `effect_id`. It writes one JSON result into a host-owned directory mounted
   read-only at `/run/laomedo/responses`. The agent reads this for task
   progress but cannot replace or redirect the response directory. On a
   restart, a claimed request with a stored effect is answered from the
   ledger only after its repository, operation and payload digest match the
   stored request. The journal marks this as replayed; no provider call is
   repeated. The host journal and mediator ledger remain the authority for
   effects.
3. A client timeout, process crash, incomplete response, or mediator `unknown`
   result is `unknown`. The client stops and never resubmits the effect or
   allocates another effect ID for the same uncertain target. A confirmed
   result permits the next distinct, approved fake update.
4. The kill probe writes its own compact observation to `/draft/loop.jsonl`
   after each response. The host records claim and finish times separately
   with its monotonic clock, including `effect_id`, mediator status and error.
   A request written before the kill but claimed after revocation is
   agent-originated denial if the mediator returns `grant_unavailable`. Compare
   the claim time to the lease's `revoked_at_monotonic`; expiry alone is not
   called revocation. If Docker removes the container
   before the lease service can do so, service-attributed cleanup remains
   inconclusive. If the loop cannot issue a request after revocation, agent-
   originated denial remains inconclusive; a host-side denied request is only
   a boundary control.

## Required gates

- Test the claim procedure against Windows reparse points, hard links,
  oversized files and sharing violations. Static link refusal alone does not
  establish confinement against a malicious same-user host process. This
  remains a single-user local prototype, not a hosted isolation claim. Remove
  or exclude `.laomedo-req-*` from post-run hashes and selectable artifacts.
- Add credential-free tests for one confirmed request, denial after lease
  revocation, B continuity, duplicate/unknown effect behavior, malformed and
  linked files, and bridge restart. The independent bridge must not redispatch
  a request after an uncertain prior outcome.
- Run a no-model Docker check through Codex `command/exec` that writes a
  request and receives a host-journaled fake response while network stays
  disabled. Check that no mediator bearer or provider credential is mounted.
  In the network-refusal control, first show the same endpoint is reachable
  through plain Docker to isolate Codex's permission denial.
- Freeze the revised task, client, host harness, image, code and skill hashes;
  get one substantive independent review. Only then spend the approved four
  model turns, with the first turn's content-free `auth.json` denial probe.
