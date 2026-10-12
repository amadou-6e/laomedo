# EXP-139 task-only amendment, 2026-10-12

AMENDMENT-05 was approved, reviewed and activated at source
`6f6a5c7e7936adfe8534e62cbd6dcdd5a9747e29`. Its one fresh success turn
completed with native trace closure but returned task failure. The imported
graph accepted that failure and routed it without publication. The ledger is
5/10, with zero provider push or PR attempts. All prior results are retained.

The preserved checkout has detached HEAD and no local run branch. The native
helper requires the configured local branch to resolve to the pushed commit.
It returned `remote_helper_failed` before writing a helper journal or mailbox
request. The network-none dummy control reproduces this missing-branch failure
and succeeds through the same helper after explicitly creating the run branch.
That control uses no model login or real provider.

The owner approved a task-only recovery. Add an explicit instruction to create
`exp139-20261011-a` from the detached baseline before committing, without
altering the report or other tasks. Use a fresh request and authority invocation
identity, retain all seven consumed request digests, and freeze source and
input hashes before submission. Do not repeat the old success request or the
already-proven failure/rejection cases.

No permission, transport, credential custody, repository, branch, image, network,
port, supervisor or publication behavior changes. The total cap stays ten,
preserving five used turns. One experimental push and one draft-PR attempt
remain the maximum. Commands keep network-off and exact auth denial; the relay
remains subject to AMENDMENT-05's accepted same-UID/process-attachment residual.
Unknown provider effects stop the campaign and are never blindly retried.

Activation requires the reviewed clean source, exact frozen manifest and final
passing CI. Archive AMENDMENT-05 activation, inputs, logs and result before
applying the new task. Leave any published test branch and draft PR for review.
