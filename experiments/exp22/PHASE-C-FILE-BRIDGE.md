# Phase C file mediation bridge proposal

The pinned Codex permission profile disables network access for agent
commands. The credential-free `command/exec` probe returned `DENIED`, so the
direct `node /run/laomedo/mediate.mjs` HTTP task is not eligible for a model
turn. This design keeps that permission profile unchanged. It replaces only
the agent-to-mediator transport for the bounded local Phase C route.

## Boundary and ownership

- The agent container writes requests into its own disposable `/draft` mount.
  It receives no GitHub provider credential, runner API token, mediator bearer,
  or host service state path. Its Codex login volume remains the separately
  approved local prototype limitation documented in the Phase C protocol.
- An independently started host service owns the mediator store, fake
  transport, lease supervisor, and file bridge. The bridge survives a kill of
  the runner process tree. The runner cannot become the sole bridge worker.
- The host derives the request directory from its private, exact run record,
  not from an agent-supplied path. It accepts requests only while that run's
  lease and scope match the recorded launch identity. The host obtains the
  run grant from the private lease directory and passes it to the existing
  mediator validator. No bearer is mounted into `/draft`.
- The fake transport records a host-side request journal containing run ID,
  effect ID, operation, monotonic receive time, terminal state or error code,
  and whether a fake provider call occurred. It records no bearer, raw body,
  login, or provider response. This journal, not agent-written files or stdout,
  is the authority for effect attribution.

## File protocol

1. The agent client writes a bounded JSON request to
   `/draft/.laomedo/requests/<unique>.pending`, closes it, then atomically
   renames it to `<unique>.json`. The host refuses duplicate request names,
   links, reparse points, non-regular files, oversized bodies, and malformed
   JSON. It never follows an agent-selected path outside the exact inbox.
2. The host invokes the existing mediator once with the request's scoped
   `effect_id`. It writes one JSON result to
   `/draft/.laomedo/responses/<unique>.json` by atomic replacement. The agent
   may read this for task progress, but it can forge files in `/draft`, so it
   cannot use the file as proof of authorization or completion. The host
   journal and mediator ledger supply that proof.
3. A client timeout, process crash, incomplete response, or mediator `unknown`
   result is `unknown`. The client stops and never resubmits the effect or
   allocates another effect ID for the same uncertain target. A confirmed
   result permits the next distinct, approved fake update.
4. The kill probe writes its own compact observation to
   `/draft/.laomedo/loop.jsonl` after each response. The host records receipt
   time separately with its monotonic clock. If Docker removes the container
   before the lease service can do so, service-attributed cleanup remains
   inconclusive. If the loop cannot issue a request after revocation, agent-
   originated denial remains inconclusive; a host-side denied request is only
   a boundary control.

## Required gates

- Reconcile request-file path handling with Windows reparse-point and rename
  behavior. Static link refusal alone does not establish race-free file
  confinement against a malicious same-user host process. This remains a
  single-user local prototype, not a hosted isolation claim.
- Add credential-free tests for one confirmed request, denial after lease
  revocation, B continuity, duplicate/unknown effect behavior, malformed and
  linked files, and bridge restart. The independent bridge must not redispatch
  a request after an uncertain prior outcome.
- Run a no-model Docker check through Codex `command/exec` that writes a
  request and receives a host-journaled fake response while network stays
  disabled. Check that no mediator bearer or provider credential is mounted.
- Freeze the revised task, client, host harness, image, code and skill hashes;
  get one substantive independent review. Only then spend the approved four
  model turns, with the first turn's content-free `auth.json` denial probe.
