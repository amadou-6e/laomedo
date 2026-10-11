# EXP-104 amendment 20: S6 result and consumed identity

Date: 2026-10-07. Status: frozen after the single S6 run and before
post-result code changes. The user-approved identity
`exp104-s6-20261007-01` ran once at source
`a32d5ed8173b4d7a16f3ab75b3ec127da822f945` and returned harness
status `scoped_candidate_pass`. It used the literal *new-branch*
post-loss request required by the frozen live protocol. The machine
observation, dry-run record and provider-attempt journal remain in the
private state until copied byte-for-byte into this evidence directory.

No model turn was used. The A marker push was confirmed; the subsequent
request for `exp104-s6-20261007-01-a-denied` returned 403
`grant_unavailable`, with unchanged provider-attempt count and public
read-back 404. Runner-loss detection and revocation now carry host
monotonic timestamps. An independent public read found only the intended
A branch at the recorded commit; B, C and the denied branch were absent.
Exact S6 containers and recorded processes were absent after the run.
The post-run exact-token scan found zero hits across 68 S6 files. The
created A branch must remain for review.

The next code revision must add S6 to the consumed-identity guard. Copy
the three sanitized generated evidence files, preserve their committed
bytes, pin their hashes, and assess the full acceptance conditions rather
than treating the harness status as final acceptance. The selected token's
exclusive repository scope is user-attested, not independently exposed by
the GitHub API. The prescribed independent Claude reviewer returned
`native_error`; a labelled self-review and passing local/CI checks preceded
the run, but no independent reviewer approval is claimed. S3's earlier
uncertain effect remains `unknown` and is never retried. No second S6 run
or fresh identity is authorized by this post-result amendment.
