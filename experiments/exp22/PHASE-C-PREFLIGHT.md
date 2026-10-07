# EXP-22 Phase C credential-free preflight

The [Phase C protocol](PHASE-C-PROTOCOL.md) was committed at `fca851a`
before this check. The opt-in Docker test was committed at `edff4eb` before its
recorded rerun. On 2026-10-07, that rerun exited 0 with both cases passing:

| Case | Observed |
| --- | --- |
| Read-only synthetic capability through Docker Desktop | Container client reached the loopback fake host endpoint and returned its fixed response. The bearer stayed in a read-only mount, not the command arguments. |
| Separate A and B grants through the real mediator store and HTTP endpoint | A's first request was confirmed; after exact `revoke_run("run-a")`, a new A request returned 403 `grant_unavailable` without a fake-provider call; B's request was confirmed. Exactly two fake-provider calls occurred. |

The local proof transcript is ignored by Git at
`claude-review.local/phase-c-docker-preflight.txt`, SHA-256
`960f69e0a4fcf592be04fb30ad68d1ea310a79d7a0afa0eddee9afce61e727255`.
The pinned test image configured by the runner is
`laomedo-codex-boundary:0.159.2`, ID
`sha256:7b79ce12be47d6c8262dd4043895112d204416bda5cd891d124775df55587239`.
The host suite passed 319 tests with 8 skipped when the opt-in Docker check was
not enabled. No model turn, GitHub credential or provider call was used.

This proves the container-to-mediator capability route and durable grant
revocation in one credential-free check. It does not test the lease service's
loss detection, a runner-tree kill, a real Codex turn, a real GitHub write,
Langflow Stop or Linux service-manager ownership. Those remain Phase C gates.
