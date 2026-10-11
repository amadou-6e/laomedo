# EXP-104 amendment 13: first-slice scope and lock-free classification

Date: 2026-10-07. Status: frozen before the S3 run. No S3 effect has been
attempted. Amendments 01–12 and both D2 observations remain historical.

The independent recheck of amendment 12's code found that classifying a Git
push inside a SQLite write transaction could hold the mediator's grant ledger
lock during a large fetch. The corrected path must authenticate the grant in
a read transaction, classify immutable commit objects without a write lock,
then revalidate the grant and persist intent in the write transaction. A
regression holds classification open while another grant is renewed.

The lease-service clock is re-read per lease. Every grant issued or renewed
under a heartbeat is capped by the last heartbeat plus 58 seconds, as well
as its 50-second ordinary TTL. A stale or future-dated heartbeat cannot
renew a grant. A delayed earlier lease must not make a later stale lease
look fresh. This bounds a lost runner's grant without depending on when a
later cleanup finishes. A backwards wall-clock jump remains an untested
system-level limitation; no clock-jump claim is made.

The S3 probe uses only first-slice operations: A's exact-branch Git push and
B/C's read of the disposable repository's Actions run list. The latter is
GitHub's documented `GET /repos/{owner}/{repo}/actions/runs` read endpoint;
the narrow transport accepts only that resource or a positive job ID for
`actions_read`. The diagnostic-only general REST read used in D2 is not
granted. [GitHub's endpoint reference](https://docs.github.com/en/rest/actions/workflow-runs#list-workflow-runs-for-a-repository)
describes the list operation and Actions read permission.

S3 requires `--token-key GH_LAOMEDO`, a fresh S3 identity and an explicit
`--scope-confirmation selected_repository_only` before state creation or
provider contact. That flag records the user's repository-selection
confirmation; it is **not** proof by itself. The controller must also
verify the selected token's principal, target repository and writable
permission with read-only provider calls, and must not treat a token that
can read a public repository as proof of exclusive repository scope. If the
provider-enforced repository selection cannot be corroborated, S3 stops
before its first write. The result remains a candidate until reviewed.

The synthetic runner, file-backed host custody and manually started services
remain unchanged limits. S3 cannot establish production browser/token
connection, deployed service identity, complete `git`/`gh` parity, real-agent
cancellation or Q11 acceptance. No automatic retry follows an uncertain
provider response.
