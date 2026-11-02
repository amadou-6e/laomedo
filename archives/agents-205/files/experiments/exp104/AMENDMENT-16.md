# EXP-104 amendment 16: S4 dry-run result and post-failure safeguards

Date: 2026-10-07. Status: frozen after the one-shot S4 probe and before
subsequent code changes. S4 at code `c464040` stopped at the non-mutating
Git dry-run with exit 128 and fixed category
`authentication_or_authorization`. The private helper emitted the selected
token in a local-only self-check. No live GitHub push, mediator dispatch,
runner, container or model turn occurred; the S4 A ref was absent on a
subsequent read-only lookup. S4 is consumed despite this preflight stop.

The next code revision must add `exp104-s4-20261007-01` to the consumed
identity guard and apply that guard even when `run()` is called directly.
The failure-record path must retain an `incomplete` record if a private
diagnostic line is malformed, without copying raw diagnostic text. Where a
mediator database exists, a read-only lookup may include the exact durable
state for A's effect in a failure observation; failure of that lookup must
not hide the original error. Tests must cover both safeguards and must check
that the dry-run credential is present during the child call, not only gone
afterward. The S3 results must not imply public `ls-remote` proved token
acceptance.

This amendment authorizes only local code, tests and evidence recording. It
does not authorize a fresh live GitHub write. Before a new live identity is
frozen, determine whether the selected token has the repository's `Contents:
Read and write` permission and can authenticate for Git over HTTPS. The
observed category is a heuristic, not a precise GitHub rejection reason.
Do not expose token bytes, token hash or raw Git output in the repository.
EXP-104 acceptance, draft promotion and Q11 remain open.
