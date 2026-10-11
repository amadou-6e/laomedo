# EXP-104 amendment 14: classify nonzero Git push diagnostics without changing uncertainty

Date: 2026-10-07. Status: frozen after the incomplete S3-01 attempt and
before the diagnostic code change. S3-01 is consumed and will not be
retried. Its attempted branch returned 404 on a subsequent read-only lookup,
but the recorded mediator outcome remains `unknown`.

The next code revision may append a **private, fixed-vocabulary** diagnostic
entry when Git exits nonzero during a mediated push. It may record the numeric
exit code and one category (`authentication_or_authorization`,
`remote_rejected`, `network_or_transport`, or `unclassified`). It must never
persist raw stdout/stderr, token bytes, a token hash, or an authenticated URL.
The category is diagnostic only: every nonzero exit continues to produce the
same durable `unknown` effect, without a resend. A test must inject secret
bytes into Git's output and prove that neither the journal nor the exception
contains them. Another test must show a nonzero push still yields `unknown`.

The already completed read-only selected-credential `git ls-remote` and
local-bare-repository push narrow, but do not identify, the live failure.
No new live effect is authorized by this amendment alone. A separate fresh
identity and checked protocol revision are required before another GitHub
write. EXP-104 acceptance, draft promotion and Q11 remain open.
