# EXP-22: early runner identity and cancellation boundary

Issue: https://github.com/amadou-6e/laomedo/issues/22.
Source base: merged Laomedo `develop` at
`0ead228a0adea44afd0467dea4acec93177af0b9`.
Related merged specs: timeout/effect contract
`7f6760e22cbdd0128e608a6591a1c94bdfd685bf` and earlier synthetic
EXP-66 evidence. This protocol is prospective; no #22 case has run yet.

## Question and falsifiers

Can a local runner durably acknowledge a unique, queryable run ID before a
new agent turn finishes, then distinguish a cancellation **request** from
confirmed remote stop while retaining partial raw events? Fail if a retry
with the same request identity dispatches another turn, a changed payload
reuses that identity, pre-dispatch cancellation launches a turn, a cancellation
response alone is reported as confirmed, a lost response silently starts a
second run, or a restart automatically replays an uncertain run.

## Phase A: zero-model implementation and synthetic checks

Preserve the current synchronous endpoint for existing callers. Add a
separate asynchronous start with a caller-supplied idempotency ID, durable
request binding, early run acknowledgment and read-only status. The request
identity belongs to the complete canonical request, not a POST attempt.
Return one stable run ID for an exact duplicate; reject a conflicting body.
Record the reservation before acknowledging or starting the worker. Do not
dispatch the worker until the acknowledgment is written to the HTTP response.
On restart, expose a previously reserved/active record as interrupted or
unknown, never silently resume or redispatch it.

Use a credential-free fake transport and existing local-only authenticated
HTTP fixture. Test: normal acknowledgment and terminal poll; cancellation
before worker execution; cancellation while a fake tool call blocks; duplicate
POST before and after terminal state; conflicting duplicate; lost-response
retry; timeout/status race; restart of a saved pending/running record; and
retained partial raw events. Include a negative control that would fail if a
second turn were started. Inspect the recorded turn ledger, not only HTTP
status. No Docker image, model turn, personal credential, GitHub write or
external effect is permitted in Phase A.

## Phase B: real runner (separate authorization gate)

Only after the async API, Langflow handoff and specs are reviewed, freeze a
new bounded real-runner amendment naming the model, prompt, turn count,
timeout, disposable workspace/container, credentials boundary and exact
cancellation points. Cover cancellation before native thread creation and
during an active tool call, and inspect the native runner status, surviving
events, container state and Laomedo IF-06/07 trace. The current instruction
does not specify a model-turn/compute cap, so Phase B must **not** dispatch a
model turn until that cap is explicitly recorded. No generic rerun of an
uncertain POST is allowed.

## Interpretation boundary

An early run ID and accepted cancel request do not by themselves establish
remote cancellation. Langflow UI Stop propagation, native turn interrupt and
container termination must be observed independently. A synthetic success
does not accept first-slice Q11; real-runner checks and positive cancellation
evidence remain required under #22.
