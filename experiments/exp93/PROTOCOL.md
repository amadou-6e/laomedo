# EXP-93: exact-container lease integration

Frozen before the first process-kill run. Issue: Laomedo #93. Governing specs:
`amadou-6e/specs` `d3c888498e3e9be2f5a1248ae4d949624bc6ba97`, especially
`projects/laomedo/subsystems/agent-execution/design/decision-readiness.md`
Q01/Q02/Q25. Implementation base: Laomedo `develop`
`9414c7ed24c5eaa05e9bd1a517ead1f2ae1a11f2`.

One fresh temporary state and one runner child are permitted. The child starts
one labelled, non-model `python:3.9-slim` sleeper using the actual runner's
container reservation and independent lease. A second, similarly named but
unowned sleeper is a negative control. The parent waits until both are directly
inspectable, verifies the owned name/labels and saved reservation, hard-kills
only the runner child once, then observes Docker and the durable record without
restarting or redispatching the run. A new runner performs the startup sweep.

Acceptance: the independently supervised exact owned container is absent within
60 seconds after the child kill; the unrelated sleeper remains running; the
saved run is interrupted with verified cleanup after restart; no turn ledger
exists. If a container identity conflicts, cleanup must refuse it. The probe
records timestamps and exact Docker identities, but never credentials, raw
model events or host paths. It refuses to overwrite an existing observation.

Only the two exact containers created by the probe may be removed, after their
name and experiment label are checked. No model turn, GitHub write, credential
grant or production workspace is part of this test. The result cannot prove
recovery of a real model turn or revocation of a future scoped push grant.

Any setup failure before the child starts may be diagnosed and retried with a
fresh identity. Once the child may have launched a container, no case retry is
allowed without a recorded amendment and inspection of the previous state.
