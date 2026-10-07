# EXP-104 synthetic process control

Status: synthetic control passed; **live scoped-GitHub-identity acceptance has not run**.

The base [live protocol](LIVE-PROTOCOL.md) remains frozen. Amendments
[01](AMENDMENT-01.md), [02](AMENDMENT-02.md), and [03](AMENDMENT-03.md)
were committed before their affected runs. The v1 and v2 observations remain
historical; v2 did not test a surviving run because both grants belonged to
the killed lease service. The v3 run used probe code at `9109bbc`, with two
separate lease-service processes and one credential-free mediator process.

Probe provenance: initial probe code `c18756a` was changed by diagnostic
commit `a1d9393` and recording commit `566d19c` before the first committed
observation (`b7eb9e1`, v1). Two initial attempts were stopped by Windows
`taskkill` access denial before any measured case or provider call. One
elevated, stdout-only diagnostic run completed but was not committed and is
not acceptance evidence. The later v2 observation (`85bd82e`) used probe
`2c90ded`; the v3 observation (`1198406`) used probe `9109bbc`. No v1 or v2
observation was overwritten or silently substituted for v3. This records the
known developmental attempts; it does not claim that those earlier diagnostics
provide independent replication.

The machine-written [v3 observation](process-observation-v3.json) is committed
at `1198406` as Git blob `d9f9d2a3e5674ac818b699cc030d23337f52affb`.
Its committed-byte SHA-256 is
`FE37A2AF147B6F6DAA5ACADF42018241FD240CDB1621E2B0F9899CDE769E6FB7`.
It contains no bearer, GitHub token, request body or private path.

The probe killed only lease service A (PID 9608). The mediator (PID 15420)
and lease service B (PID 17296) were still alive afterward. At 0, 15, 30 and
45 seconds after the kill, both synthetic writes returned 200. At 60 seconds,
A returned 403 while B still returned 200. The ordered journal has exactly
nine provider calls, matching the nine 200 responses; the denied A request
added no provider call. This demonstrates fail-closed expiry for new requests
after the service A hard kill while the unrelated B run remains usable. It
also shows that A writes remained possible throughout the roughly 60-second
expiry window. The last-renewal estimate is wall-clock-derived and is not
used to assert a subsecond deadline.

This is **not** the requested live acceptance result. It did not kill a
runner, launch an agent or container, use a scoped GitHub identity, push a
branch, read GitHub back, test actual credential retirement or prove the
full `git`/`gh` adapter. Those cases remain open under #104 and the live
protocol. No model turn or GitHub token was used.

## Broad-token live diagnostic D2, first identity (incomplete)

The user created public disposable repository
`ga84jog/laomedo-exp104-disposable-20261007` (ID `1408647759`). Amendment
[08](AMENDMENT-08.md) froze its one-shot README initialization; the response
confirmed baseline `1f1a505f2fbd31993a7946924a9bec5a27bb15c1`.
Amendment [09](AMENDMENT-09.md) and probe code at `fceaecc` preceded the
first mediated push. The probe used the selected `ga84jog` token, not ambient
`gh`; the token was broad and the host-file connection test-only, as
amendments [05](AMENDMENT-05.md) and [06](AMENDMENT-06.md) disclose.

The machine-written [first observation](live-observation-d2.json) records
identity `exp104-d2-20261007-01` and an incomplete `ready_timeout`. Its
committed-byte SHA-256 is
`95A5A579DFBA4F943ACEE6D5F89616C035B43A3BCEEAD12A4A81B8799AADA3D0`.
Independent read-back found A's new branch at exactly
`919fc96cd89ac5c972a36cef4296780544133a8b`. The local non-secret
provider-attempt journal contained one `git_push` and two
`api_rest_read` attempts, with no post-revocation push attempt. A's saved
lease result reported `heartbeat_lost`, revocation and verified exact
container removal. B's restart result reported revocation and verified
removal. C's lease was accepted but its heartbeat expired and the container
was never observed. The probe stopped there; no C provider request occurred.

The first harness wrote detailed progress only on full completion, so the
exact runner-kill timestamp and response details are not in committed raw
evidence. Do **not** infer a measured 60-second bound or full diagnostic pass
from this run. The private state remains local for inspection, while the A
branch remains in the disposable repository. Identity `-01` is consumed and
will not be retried. Amendment [10](AMENDMENT-10.md) freezes a fresh identity
and incremental evidence capture.

The local-only [Docker preflight observation](docker-preflight-observation.json)
shows the pinned image launching as an exact labelled container and verified
removal, with no credential or model. Its committed-byte SHA-256 is
`4718CD69E586671541920AFD14F10382821B1F807035016D244E48AAD8C89C1F`.
The B/C lease timing points to the startup sweep occupying the lease service
while C waited for admission; this is a diagnosis, not a captured C exception.
Amendment [11](AMENDMENT-11.md) requires the B sweep to finish before C starts.
