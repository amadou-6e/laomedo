# EXP-104 amendment 17: S5 selected-token retry

Date: 2026-10-07. Status: frozen before S5 code changes or provider contact.
The user requested another attempt after S4's non-mutating Git dry-run failed.
This request authorizes one fresh bounded attempt, not reuse of an earlier
identity or an automatic retry of any uncertain write. GitHub's exact reason
for S4's exit 128 remains unknown; do not claim that the token setting was
independently verified merely because the user requested a retry.

The next identity is `exp104-s5-20261007-01`, connection
`exp104-s5-selected-gh`, with its distinct A/B/C branches, run IDs, leases,
containers and effect IDs. The selected `GH_LAOMEDO` token and disposable
repository remain the only credential and target. Preserve the consumed
identity guard for D2, S3 and S4. S5 must require the selected-token
confirmation and use the same non-mutating Git `push --dry-run` plus
read-only ref check before any mediated write. The dry-run's exit/category
may be recorded, but raw Git output, token bytes and token hashes must not
be persisted. A nonzero preflight stops this identity; it is not retried.

Before S5, harden the failure handler so malformed or partially written
progress, plan, dry-run or provider-attempt files cannot hide the original
error or prevent an `incomplete` record. Keep allowlisted structured data
only. Make progress checkpoints atomic where practical and cover the
failure path with no-network tests. Extend scoped-candidate status and
token checks to S5 with tests. Review the changed code and run the affected
suite before the attempt. Pin its exact source SHA at launch.

If the dry-run and all mandatory preflights pass, run the frozen
[live protocol](LIVE-PROTOCOL.md) once for S5 with zero model turns. Stop
immediately on uncertain write/effect state; never resend that effect.
Inspect only the exact disposable refs and containers, record a sanitized
machine observation and committed-byte hash, and leave created refs in
place for review. No run is a first-slice pass unless all original
acceptance conditions hold. Draft #97/#105, EXP-104 and Q11 remain open
until their separate acceptance and review boundaries are satisfied.
