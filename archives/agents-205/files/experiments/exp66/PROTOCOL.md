# EXP-66 prospective live synthetic trace-integration protocol

Issue: https://github.com/amadou-6e/laomedo/issues/66.
Source base: Laomedo `8b3087751b79266ab3c454fe2cdfa8e15f94b097`
(`develop`), with #66 store implementation at `c4f506678de783f5be53bd7d12194c56a63bc7df`.
Governing proposed contract: specs PR #213 at
`ec0485421cf7140ef747a0215b88180bc8816870`, explicitly authorized for
implementation before review. Historical runtime evidence: EXP-65 at
Laomedo `3543a669857fe78f747f94737b3a3f4aba444290`.
Pinned runtime: Langflow 1.12.3 image
`langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0`.

## Question and falsifiers

Can a Laomedo run/trace/invocation be reserved before one live v2 Langflow
call, then retain the actual `408`, `JOB_FAILED` status reads and delayed
synthetic effect as separate receipts under that identity after reopening
the durable store? Fail if no identity exists before dispatch, the timed-out
POST is retried, any effect is omitted, `JOB_FAILED` is interpreted as no
effects or confirmed cancellation, a status read without that detail code is
called failed, or the trace becomes complete after the effect.

## Frozen run and limits

Use one fresh disposable Langflow container and volume, a localhost-only
published port and the EXP-10 in-container loopback runner. Zero model turns,
zero external/GitHub writes and no personal credentials. Verify the effective
server timeout at 3 seconds. Create a single native flow with an 8-second
component timeout and 6-second synthetic runner delay. Resolve and durably
reserve the graph/config, run, trace and invocation IDs, then commit one
dispatch attempt before the single v2 synchronous POST (15-second caller
limit). Do not retry that POST under any result.

If it returns `408` with a job ID, poll only the documented read-only
`GET /api/v2/workflows?job_id=<id>` at 0, 1, 4 and 7 seconds after the 408.
Each read has its own 5-second timeout. Before each poll, inspect the runner
journal and append any new effect receipt with a source reference; inspect
once more after the last poll. Preserve every job-status delivery. Reopen the
SQLite run store, sweep nonterminal runs, and capture its sanitized trace
snapshot without another dispatch. Record host/container clock calibration,
observed response categories, runner entry/effect counts and container
state. Remove the disposable container, volume and local SQLite copy after
capturing evidence.

One live invocation, four status reads, one synthetic effect, one container
and one named volume are the cap. Missing IDs, API errors and absent effects
are negative/inconclusive observations, not grounds to modify the protocol
or rerun. Commit any amendment before another run and assign a fresh
observation identity. Keep raw credentials and private traces out of Git.

## Interpretation boundary

This proves only a bounded synthetic integration at the pinned versions. It
does not exercise the production UI, all Langflow graph branches, a real Codex
worker, early native run identity or cancellation. #22 still owns those
real-runner checks. Even a passing synthetic trace must not close first-slice
Q11 by itself.
