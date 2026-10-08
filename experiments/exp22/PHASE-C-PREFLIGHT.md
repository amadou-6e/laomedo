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

## Pinned-route rerun after parent integration

The parent runner added pinned mediator-instance headers and stricter Docker
flags after the first preflight. The reconciled source was committed at
`f5d27bc` before another opt-in rerun on 2026-10-07. Both cases passed with
the parent `_docker_prefix` command, including the run-capability mount,
mediator-instance binding, capability revocation and B continuity. Its new
ignored local proof is `claude-review.local/phase-c-docker-preflight-v2.txt`,
SHA-256 `2c67f3dd414779e5cf510c9d18957c763f874c0f68eb822e1641d4cc0f097679`.
The first proof above remains a record of the earlier source, not the current
implementation result. No model or GitHub call was made in either rerun.

On 2026-10-08, the ordinary host suite at `e0938f4` was rerun with the
project's installed virtual environment: `python -m unittest discover -s
tests -q` passed 322 tests with 8 skipped. This is a host regression check,
not another Docker, lease-loss or model-backed result. The A/B test issues
unbound grants directly into the mediator store and calls `revoke_run`
explicitly; it does not exercise lease-triggered revocation.

## Fresh lease-loss check on the reviewed Phase C head

On 2026-10-08, the existing credential-free `exp93/service_probe.py` was run
against `0f04bd4` with the base Python 3.12 interpreter and the installed
project dependencies. The first attempt with the Windows virtualenv launcher
stopped at `service_identity_mismatch` before creating a stage: the launcher
reported a wrapper PID rather than its Python child's PID. The base-interpreter
rerun exited 0. Its ignored observation is
`claude-review.local/phase-c-service-preflight.json`, SHA-256
`0a6af467561825e9c19f208453b270dbb059af3a4d717d68ea491762c2d4cf5e`.

The runner-tree kill left the independent lease service alive. It revoked the
synthetic grant 4.566 seconds after the kill, removed the owned container after
5.14 seconds, rejected a later A write with 403, and left a lookalike
container unaffected. B continuity was checked in the separate mediator test
above. There were zero accepted A writes after revocation and
no model turn or GitHub token. Docker Engine was 27.3.1. A later `docker ps`
found no named disposable containers left by the probe.

This is a fresh lease-service and Docker kill check at the current source, but
it uses the older direct synthetic `/write` endpoint rather than the Phase C
mediator and Codex runner together. The earlier A/B mediator check and this
lease-loss check therefore remain separate evidence; the integrated Phase C
step 1 and agent-originated results are still unverified. The full host suite
at `0f04bd4` passed 339 tests with 9 skipped.
