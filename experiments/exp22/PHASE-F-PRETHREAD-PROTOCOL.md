# EXP-22 Phase F: visible Stop before native thread creation

This is a bounded local follow-up to the positive [Phase E active-tool
result](PHASE-E-RESULTS.md). It tests the other #22/Q11 cancellation point:
the browser clicks visible Playground Stop after the real runner has durably
prepared a run but before the runner sends its early HTTP acknowledgement or
starts a native worker. The shared user-extended ledger cap is twelve, with
five entries already used. Reserve one new entry before browser Send, even
though a passing pre-thread cancel should make zero native model calls.

Use the same pinned Langflow image, saved five-node flow and local runner
configuration as Phase E. The disposable server mounts only a read-only runner
API token and component code, not provider login. The existing private Codex
login volume remains available to the runner but should never be launched for
this case. Compare embedded flow component code with the pinned source before
dispatch and clear fake-task switches from the browser environment.

The test host wraps only the local runner's `/v1/runs/async` acknowledgement.
After `start_async` persists a `prepared` record, hold that acknowledgement
until the browser Stop click has caused an exact authenticated request lookup
and cancel. The native worker's ordinary response gate remains closed during
the hold. Do not alter the production runner or its permissions. Release the
acknowledgement after terminal cancellation or in teardown. If the hold fails
and a native thread starts, classify inconclusive and cancel/clean up exactly.

Pass requires one browser Send and visible Stop click, one prepared run,
one matching request lookup and cancel in the click-to-terminal-to-browser-close
order, terminal `cancelled` with `cancel_confirmed=true`, no turn-ledger file in
the run state, no native thread ID, no native command events, no Codex container
launch and no second run. Browser disconnect and host fallback cancellation
cannot count. Persist private raw browser, route and runner records plus only
sanitized hashes and counts in Git. A timeout or ambiguous submission spends
the ledger entry. Do not claim a durable Langflow invocation-to-runner trace
join or #93 credential revocation from this test.
