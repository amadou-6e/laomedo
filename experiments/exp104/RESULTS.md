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

## Broad-token live diagnostic D2, fresh identity `-02` (bounded pass)

The corrected probe at `4b0c2cd` used fresh identity
`exp104-d2-20261007-02`. Its [machine observation](live-observation-d2-02.json)
has committed-byte SHA-256
`AE2C85E0EE414B30EDB9A5E10557B935399C2B49AF25E8F70737A6AE3DEB9FEC`.
The [provider-attempt journal](live-provider-attempts-d2-02.jsonl) is an
exact-byte copy of the private host journal, preserved without Git newline
conversion; both source and committed target hash to
`62F69933E06927980DE4B4023B19D6CB58EBAD66B0732D29BB8C86F65178DB6C`.
The selected-token canary scan found zero exact-token matches across 65
generated state/evidence files. It does not prove general secret redaction
outside those files.

The observed sequence was:

1. Trusted A and B run scopes and labelled disposable containers were
   admitted under separate lease and mediator processes. A wrong-branch push
   was refused before provider transport.
2. A pushed one new branch, `exp104-d2-20261007-02-a`, at exact commit
   `058ad6e5fce09481a1be57c684df69f557d5ba53`. A selected-token
   read-back confirmed that SHA. B's scoped same-repository read succeeded.
3. The A runner process tree was killed once. The lease service revoked A
   **4.357 seconds** after kill completion and verified exact-container
   removal **9.480 seconds** after kill completion. A new effect using A's
   same approved branch was refused as `grant_unavailable`; the journal
   stayed at two provider attempts through the denial. A second remote
   read-back found the branch unchanged. B's read still succeeded.
4. Restarting only the lease service revoked B's old grant and removed its
   exact container. The service did not adopt the old lease. A freshly
   approved C run completed a scoped read. Its unpushed workflow-file commit
   was refused as `workflow_approval_required` before provider transport;
   the missing-run and mismatched-repository controls also refused.
   Isolated synthetic controls refused an expired grant and retained an
   ambiguous response as `unknown` without a second transport call.

The journal contains **four** provider attempts: one A push and three reads.
There is no second push, no PR or issue write, and no model turn. Independent
post-run read-back found only `main` and the two A diagnostic branches; `main`
remained at baseline. The probe's exact A/B/C containers were absent after
cleanup. The two A branches remain in the disposable repository for review;
none was deleted.

This is a **bounded diagnostic pass**, not EXP-104 acceptance. The token has
`All repositories` access rather than provider-enforced repository scope;
its host-file custody is test-only. A synthetic runner and disposable Docker
container stood in for a real agent. Production service launch, browser/token
account connection, real `git`/`gh` parity, real-agent cancellation and Q11
remain unproven. Drafts #97/#105 must not be promoted from this result alone.

The tested `4b0c2cd` revision temporarily allowed `api_rest_read` in the
default first-slice approval set to perform B's control read. That was wider
than the current first-slice spec, which permits Actions read but not general
REST read by default. A subsequent implementation correction restored the
narrow default and made same-repository REST read an explicit diagnostic-only
opt-in, with a regression test for both paths. **No new live run was made
after that correction**; the observation remains pinned to the code that
actually ran and cannot prove the corrected path's live behavior.
