# EXP-104 amendment 27: retire pre-write S10 and freeze S11

Date: 2026-10-08. Frozen before S11 implementation and any S11 provider call.
The approved S10 identity `exp104-s10-20261008-01` ran exactly once and
stopped with `lease_service_unavailable` before a setup grant or provider
attempt. Its private observation has zero events and no
`provider-attempts.jsonl`. S10 is consumed and will not be retried.

S10 fixed the Windows launcher PID mismatch: the mediator and lease service
published the exact spawned PID and expected source root. The new failure was
a startup race. `service.json` was published before the heartbeat thread
created `service.alive.monotonic`; the probe waited only for `service.json`,
then the first `LeaseClient` correctly refused an unproven service. The host
service exited during cleanup and its exact process is no longer running.

The fresh identity is `exp104-s11-20261008-01`. Target, baseline, no-model
limit, four intended provider writes, A/B checks and no-retry rule remain as
in amendments 21–26, with S11 substituted for S10. The only allowed remote
repository is `ga84jog/laomedo-exp104-disposable-20261007` (ID
`1408647759`), at baseline `1f1a505f2fbd31993a7946924a9bec5a27bb15c1`.
Branches are `exp104-s11-20261008-01-a` and `-b`; abort if either branch or
PR marker exists. User approval and selected-repository-only token scope
confirmation carry forward. No earlier identity is retried.

Before any setup grant, S11 must observe the exact host service still alive,
with matching published PID, both wall and monotonic heartbeat files present
and fresh under the lease service's own staleness limit. Wait only for this
bounded readiness condition; a timeout fails closed. Add a test that first
withholds the monotonic heartbeat and then publishes it, proving the gate
waits. Preserve the strict process and module-origin checks. Pin S11 code and
tests after implementation and obtain a new positive independent review of
the exact final head before the first provider write.
