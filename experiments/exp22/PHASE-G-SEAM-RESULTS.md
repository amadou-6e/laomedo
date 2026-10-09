# Phase G: visible Playground first-call seam

The [design draft](PHASE-G-JOIN-DESIGN.md) proposes reserving a Laomedo
invocation when the Langflow component first calls a host bridge, before any
runner POST. This credential-free probe checked that a visible Playground Send
can reach that seam and that visible Stop can still address the same client
request identity. It does not implement the bridge or complete #22.

## Frozen inputs and method

- Pinned Langflow image:
  `langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0`.
- Saved flow: `examples/native-codex-node/flow.json`, SHA-256
  `58fb018b5043c645744b375d0b2f015130b2d84ca0ccf99946bfd40b7ada69ed`.
- Probe: [phase_g_playground_seam.py](phase_g_playground_seam.py), SHA-256
  `f04ba933c49f619519db37878862d32db8d832d9533b2467a00b4f362882ee5b`.
- No real runner, provider credential or model was used. A disposable Langflow
  container called a fake HTTP bridge on the host. The bridge used
  `WorkflowRunStore` to reserve and bind one synthetic runner identity before
  returning an emulated early acknowledgement. Browser automation clicked
  Playground Send and then Stop. Its task was synthetic.
- Private state is under
  `%LOCALAPPDATA%/Laomedo/exp22-phase-g-seam-20261009-c/`. It contains the
  disposable HTTP token, browser profile and SQLite database and is outside
  Git. Only this sanitized account is published.

## Observed result

The final run of the probe passed. One visible Send reached the fake bridge,
which wrote a reservation and synthetic runner binding to `WorkflowRunStore`.
No separate runner start or acknowledgement occurred. After the visible Stop
click, the fake observed a lookup by the same client UUID, then an exact
cancel, both before the browser closed. Reopening the host SQLite store found
the bound synthetic runner ID and cancellation receipt. The client UUID
differed from the host-minted invocation ID; this probe used the invocation ID
as its synthetic runner request ID. A host-side self-test of the fake returned
202 for the same body and 409 for a changed body under that UUID. Those
responses do not test Langflow or a product bridge's retry behavior. The saved
graph in the host record came from the repository fixture, not from the
executing Langflow graph. The shared model-turn ledger stayed **6/12** because
the probe submitted zero model turns. The disposable Langflow container was
absent afterward and the fake bridge stopped.

This establishes a feasible first-call and Stop routing seam in the installed
runtime. It does **not** show the real pre-POST-to-ack ordering, a real runner
POST, native cancellation,
credential isolation, attestation of the executing editor graph, a Langflow
database restart, or a durable cross-store trace join. The fake bridge does
not yet implement the client-UUID cancel race before its first acknowledgement.
The browser observer captured the build monitor request but not an exact Send
route, so no claim about the frontend endpoint follows from this probe.

Claude's focused design recheck accepted the lazy-reservation direction and
identified the client-UUID Stop race as a required implementation item. The
reviewer inspected the revised design document only; it did not freshly read
the component, contracts or pinned Langflow image. The source and runtime
checks above are separate observations, not part of that review.

## Next gate

Implement a host-owned bridge and make the component use it in an opt-in,
disposable run. Test client-UUID cancellation before acknowledgement, unknown
POST reconciliation and crash/restart without redispatch. Keep the saved flow
revision distinct from the unverified executing graph. Only then spend a
remaining model turn to verify the real runner binding through Playground.
