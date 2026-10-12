# EXP-139 AMENDMENT-06 result, 2026-10-12

The owner-approved task correction created the run branch successfully. Run
`d5168375-57e8-4c1e-9cf5-a71e9d49b0d7` reached the actual Windows-host mailbox
and froze a bundle under the scoped mediator. No provider write occurred.
The helper stopped with `stage_pending_no_retry`; native execution closed,
but the downstream contract rejected the final submission and selected
rejection. The machine observation is [AMEND06-OBSERVATION.json](AMEND06-OBSERVATION.json).

The frozen receipt lacks `advertised_commit`, as its producer contract specifies.
The composition nevertheless indexed that field inside its verification
thread, swallowing the resulting error. There is no verification journal or
verifier container for this attempt. This is a host integration bug, not a
network or sandbox denial. The publisher's artifact reader made the same
incorrect field assumption. [AMENDMENT-07](AMENDMENT-07.md) corrects both reads
using the existing checksum-validated private bundle reader.

Executed source was `190de01a6e2157ca521ba91a1aaea2b72fe2e742`, manifest
`6e7b5b4bbdc8debd2375685cd66a15f43db5fd5315d95a1d1e548a6961cc560c`.
Ledger 6/10, zero provider attempts, grants revoked and container cleanup
verified. Both owned host process trees were stopped; raw traces, workspace,
bundle, consumed identity and previous observations remain private and retained.
This establishes actual relay reachability and freezing, not verified staging,
successful publication or #139 completion.
