# EXP-104 synthetic process control

Status: synthetic control passed; live scoped-GitHub-identity attempts have
run, but **full protocol acceptance has not passed** (S5 harness pass with
recorded deviations).

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

## Selected-repository S3 attempt `-01` (incomplete)

The user confirmed that `GH_LAOMEDO` is a fine-grained token selecting only
`ga84jog/laomedo-exp104-disposable-20261007`. The probe at `aedeef4a` used
fresh identity `exp104-s3-20261007-01`, the host-only selected token, the
unchanged disposable `main` baseline, and the narrow Actions-read preflight.
The frozen amendments [12](AMENDMENT-12.md) and [13](AMENDMENT-13.md)
preceded the run. This user confirmation is not an independent GitHub
attestation that no other repository is selected.

The first command failed while importing the local package, before state
creation or provider contact. With the local checkout added to `PYTHONPATH`,
the same unused identity entered the one-shot probe. The wrong-branch control
returned 403 before transport. A's exact-branch push wrote **one**
provider-attempt journal entry before entering the transport, but the
mediator returned HTTP 200 with effect state
`unknown`; the probe stopped at `a_push_not_confirmed_no_retry`. It did not
retry the push, kill the runner, or execute B/C cases. The machine-written
[observation](live-observation-s3-01.json) has SHA-256
`5C2DD78CE0B8C3D9788E4B06848FC6FDBCBEEDD695C3B36D635C7387BE7C74AF`
and matches the private original byte-for-byte. The committed
[single-entry provider-attempt journal](live-provider-attempts-s3-01.jsonl)
records only the operation, branch, commit and time; its newline is
normalized from the private journal, so it is not presented as an exact-byte
copy.

A subsequent read-only GitHub ref lookup returned 404 for S3's A branch.
This is useful read-back evidence, **not** proof that the unconfirmed push
could not have taken effect or appeared later. A read-only `git ls-remote`
configured with the selected host-side credential helper succeeded for
`main`; the public repository may not have used that credential, so this
does not establish token acceptance or explain the `unknown` result.
The probe verified removal of its exact A and B containers (C was absent).
An after-run exact-token scan found zero hits in 56 private state files;
the probe ended before its planned full success-path canary. No model turn
was used and no PR or issue was written in the disposable repository.

S3 identity `-01` is consumed. The live EXP-104 acceptance gate remains
open, as do draft #97/#105 and Q11. S3 did not capture whether Git exited
nonzero or another transport error occurred. Investigate that path with
non-mutating controls and freeze any next protocol revision before a distinct
new live identity; never resend this effect.

Amendment [14](AMENDMENT-14.md) was frozen after S3-01 and before a
diagnostic-only code change. The later code appends a fixed-category private
record for nonzero Git exits while leaving the durable effect `unknown` and
never persisting Git output. Unit tests cover the no-secret and no-resend
rules. S3-01 did **not** run that later code, so it has no such category.
Amendment [15](AMENDMENT-15.md) then froze consumed-identity refusal, an
end-to-end redaction test, and a non-mutating S4 dry-run preflight before
the next separate live candidate. The dry-run is a guard, not a promise that
a later GitHub write will succeed.

## Selected-repository S4 attempt `-01` (preflight stop)

At reviewed code `c464040`, the separately frozen S4 identity used the same
selected token and disposable repository. Its Git `push --dry-run` guard
exited 128 with fixed category `authentication_or_authorization`, before
mediator creation, runner launch, container launch, or live push. The
[machine observation](live-observation-s4-01.json) is byte-identical to the
private result and has SHA-256
`876EA17E29665F266A1B031E6FC240630E3555878D4ED426EC50C4301674E841`.
It records zero provider-attempt journal entries and no model turn. A
subsequent read-only GitHub lookup returned 404 for S4's A branch, and no
S4-named container existed. A local-only credential-helper check emitted
the selected token to Git, without displaying it; this narrows the failure
but does not identify GitHub's exact rejection reason.

S4 is consumed. Amendment [16](AMENDMENT-16.md) freezes local safeguards
and evidence changes made *after* this result. The category is heuristic;
the user's repository selection and API preflight do not prove Git-over-HTTPS
write permission. At this handoff, checking the token's `Contents: Read and
write` setting and Git authentication remained the next prerequisite; the
later S5 result below establishes a successful write at that time but does
not identify why S4 failed. EXP-104 acceptance, draft
#97/#105 promotion, and Q11 remain open.

## Selected-repository S5 attempt `-01` (harness pass; protocol incomplete)

The user requested another bounded attempt, and amendment
[17](AMENDMENT-17.md) froze identity `exp104-s5-20261007-01`, connection
`exp104-s5-selected-gh`, and the unchanged disposable repository before
code or provider contact. The read-only reviewer approved source
`6fc655cc4d96a09163ca544463fc4ea7f58a20bb` for this one attempt;
the full local suite and both CI jobs passed. The non-mutating Git dry-run
passed; the probe's subsequent read-only ref check would have stopped the
run had its A ref appeared before the first mediated write. This
shows the selected token could perform this Git operation; it does **not**
independently attest that only this repository was selected in GitHub.
The record does not establish whether the token's value or settings changed
between S4 and S5, so S4's Git dry-run failure has no confirmed cause.
The exact-byte [dry-run record](live-dry-run-s5-01.json) has SHA-256
`22FEDDB5E8BD5B74B027EEE24E589142903C3572031B5D515E3AE5739FD95C89`;
it contains only exit code 0 and a null failure category.

The exact-byte [machine observation](live-observation-s5-01.json) has
SHA-256 `D0F3523A398676FAD6512560E2D3453DF46FC4BE00F1A914B282A732C2DAA661`.
It records a confirmed push to fresh branch `exp104-s5-20261007-01-a` at
commit `969d50b8b2a238cac10954ee4eee0d0773b1f48c`, a confirmed B read,
and one killed A runner process tree. The independent service detected
runner loss after 4.552 seconds and revoked A's grant after 4.556 seconds
(lease-service wall-clock deltas from the recorded kill time). The grant
remained usable during that measured ~4.56-second detection window. The
A post-loss write was denied at 4.625 seconds (probe monotonic delta)
with HTTP 403 and no additional provider call. The exact A container was
removed and verified absent after 9.657 seconds (wall-clock delta). B's
grant still completed an approved read.
On service restart, old B was denied and a newly authorized C completed
its read. Missing-run, workflow-file, expiry and lost-response controls
behaved as specified; the synthetic ambiguous write used one transport
call and remained `unknown` on repeat.

Four provider calls are recorded in total. The negative controls added
none. The exact-byte [provider-attempt journal](live-provider-attempts-s5-01.jsonl)
has SHA-256 `31DD9E35A109450112DCDDEED2E95665923F31063E5DC85F3FFA3BEB9733456A`;
its four entries contain only operation, repository, timestamp and (for
the push) branch and commit. A separate credential-free read-back found
only S5's A branch at the same SHA, not S5's B or C branches. The probe
verified all exact S5 containers absent; a post-run process check found no S5 runner,
lease-service or mediator process. Its in-run canary found zero exact-token
hits in 67 files; a separate post-run scan, including hidden checkout
files and the sanitized observation, found zero hits in 68 files. No model
turn was used. The probe-created A branch is intentionally left for review,
not deleted.

The machine reported `scoped_candidate_pass`, but the literal frozen
protocol is **not complete**: its post-loss control requires a new unique
branch, whereas S5 used a fresh effect ID on A's already approved branch.
The [retrospective deviation record](DEVIATION-S5.md) explains why this
is an informative revocation isolation test but cannot be counted as the
new-branch criterion. This result is not EXP-104 acceptance or permission
to promote drafts #97/#105. The token's exclusive repository scope remains
user-confirmed rather than independently verified. The probe used a
synthetic runner and disposable container, not a real agent. Production
account connection, complete `git`/`gh` parity, real-agent cancellation,
and Q11 are still open. S3's earlier A effect remains `unknown` and was
never resent. Amendment [18](AMENDMENT-18.md), frozen after S5, marks the
S5 identity consumed before any further code change.
