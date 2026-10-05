# EXP-65 prospective post-timeout status protocol

Issue: https://github.com/amadou-6e/laomedo/issues/65.
Source base: Laomedo `99ff3801faa821f731158a152f7a5129dfd62368` (`develop`).
Governing specs: `amadou-6e/specs` merge
`92bcdcdc189809920bbf905fa88fcc4b841f531b`, Langflow-integration
Q11/E03 and EXP-10 evidence. Runtime: Langflow 1.12.3 image
`langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0`.

## Question and falsifiers

Does the job ID in a synchronous v2 `408 EXECUTION_TIMEOUT` allow read-only
inspection of the job while a synthetic remote effect is still pending, and
after the effect? Which of those facts, if any, can be represented as a partial
IF-06/07 trace? Do not infer cancellation from `408` or from a job status alone.
A safe-timeout claim fails if it omits a late effect, reports an unobserved
cancellation, or turns missing status into confirmed completion.

## Frozen case and limits

Use the EXP-10 pinned native component and deterministic in-container loopback
runner, in one fresh disposable Langflow container/volume with localhost-only
published port. Configure and read back the v2 synchronous server ceiling at
3 seconds; use a 6-second runner delay, 8-second component HTTP timeout and
15-second caller timeout. Make **one** v2 `POST /api/v2/workflows` invocation.
Do not retry it. The runner records one entry and one durable synthetic effect.
Zero model turns, zero external service/GitHub writes, no personal credentials.

On receiving `408`, save its status/code/job ID and caller monotonic elapsed
time. Poll only the documented read-only `GET /api/v2/workflows?job_id=<id>`
at approximately 0, 1, 4 and 7 seconds after the response. These offsets
span the expected late effect and give a bounded terminal observation. Use a
fresh timeout of at most 5 seconds per status read; a failed read is evidence,
not a reason to retry the timed-out POST. Preserve response status, key names,
job status/error, graph/run identity if present and an explicit absence marker.
Read the runner journal after the last poll. Capture container state. Also
measure host/container UTC clock offset before and after the invocation; do
not rely on sub-second cross-clock ordering without that calibration.

The total synthetic runner delay is 6 seconds, the post-408 observation window
is at most 7 seconds plus read time, and the experiment stops after one call.
Do not amend the case, offsets or limits after seeing the result. If the API
rejects status lookup or never exposes a job ID, record that as the negative
result. Do not discover or invoke undocumented endpoints after dispatch.

## Interpretation boundary

The API's job status is not a Laomedo IF-06/07 trace. This probe can establish
whether a read-only job lookup preserves state after `408`; a separate
integration test is required to prove that Laomedo persists partial/unknown
trace events and reconciles effects. Real Codex runner cancellation remains
under #22. Pin code revision and sanitized observation hashes in the evidence
record; retain this protocol unchanged and commit any amendment first.
