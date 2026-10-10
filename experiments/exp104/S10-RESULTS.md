# EXP-104 S10: pre-write heartbeat readiness failure

S10 identity `exp104-s10-20261008-01` was invoked once at reviewed head
`b7db30c67d1644c1107059fb589cb100deb24653`. It stopped with
`lease_service_unavailable` before setup grants, Docker runners or provider
mutations. Its private observation reports zero events, zero model turns and
the expected host-service PID and module root. There is no
`provider-attempts.jsonl`. S10 is consumed and will not be rerun.

The directly spawned host service published matching mediator/lease PIDs.
However, `service.alive.monotonic` was absent when the first `LeaseClient`
checked service health. The probe waited for `service.json` but not for the
heartbeat thread's first complete publication. The lease client refused as
designed; no write path was reached. The exact host-service process was no
longer running after cleanup. The private state remains under its single-use
name for audit; it is not copied into this repository.

Amendment 27 freezes S11 with a bounded readiness check for both fresh
heartbeat files before any setup grant. S10's positive pre-run review is not
approval for S11.
