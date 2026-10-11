# Mediated agent host services (staged, Windows local slice)

The agent runner can now pass a run-scoped mediator capability to its pinned
Docker image. The reusable GitHub credential remains in a host-only service.
This is **not** acceptance of #100 capability parity or the production
LocalRunner runner-loss gate. The bounded scripted-container live evidence is
recorded separately in S12 B; configuration alone does not prove it.

## Process ownership

Start `python -m laomedo.host_services` as an independently managed **host
process**, never as a child of the agent runner. Supply private state outside
the checkout, a trusted host checkout, the pinned workflow-classification
baseline, repository, connection identity/generation, and the explicit token
file/key. This process owns both the lease supervisor and credential mediator.
It binds only to host loopback and publishes `lease/service.json` and
`mediator/mediator.json` in its private state. The runner is then started with
`--lease-service <state>/lease`, `--github-authority-store
<state>/authority.sqlite`, and `--mediator-state <state>/mediator`.

The host process must be launched and monitored by the user's OS service
manager, outside the runner's process tree/control group. This repository
supplies the foreground process, **not** an installed Windows service or Linux
systemd unit. Its own failure is not a verified cleanup event; grant expiry
remains at most 60 seconds, and container cleanup on service failure is still
unproven. A production startup/survival claim requires a separately tested
service-manager deployment.

The controller—not the agent—creates the reviewed run authorization in the
same authority database before dispatch. The runner binds it once. The lease
service then issues a capability into one exact lease directory. Only that
`grant.secret` file is mounted read-only at `/run/laomedo/capability`; the
host token file, authority database, mediator database, and host `gh` login
are never mounted. The agent can send a normalized operation as JSON on
stdin to `node /run/laomedo/mediate.mjs`. The command prints the mediator's
JSON response and exits nonzero on denial. It never prints the capability.

Service and runner heartbeats are published by atomic file replacement so a
reader cannot mistake a truncated renewal for a lost process. Windows reader
locks get bounded replace/read retries; a persistent write error is logged and
the heartbeat loop keeps running, while stale timestamps still trigger loss.
The two clock values remain separate files; service-manager deployment and
failure behavior still need their own check.

The current Docker route uses `host.docker.internal` to reach a loopback-only
host mediator. A no-model test checks that route on Windows Docker Desktop.
The runner refuses mediated dispatch on other host platforms until their
container-to-loopback route is specified and tested. It also checks the
mediator's live instance identity before launching the container. Every
mediated request carries that identity, so a restarted standalone mediator
refuses an old container. The exact run capability is redacted from the
runner's captured stdout/stderr trace before persistence; this cannot stop
an agent from deliberately encoding or disclosing it elsewhere during its
valid lifetime. The credential-owning service is not started implicitly by
an agent run.

## Current operation boundary

The mediator accepts normalized `git_push`, `pr_create`, `pr_update`,
bound `pr_read`, `actions_read`, and a separately diagnostic `api_rest_read`
when the trusted grant allows them. The runner's default `/draft` snapshot
has no Git history and refuses a `git_push` grant. Its opt-in `--git-workspace`
mode prepares an isolated repository and permits that grant. The agent can
request `bundle_freeze` with only an `attempt_id`, capturing the fixed
`.laomedo-handoff.bundle` while the run and grant remain active. Host roots
come from `--runner-state` and `--private-stage`, never from the agent.
This capture does not verify Git objects or authorize a push. A separate
credential-free foreground worker, `python -m laomedo.bundle_verifier`, now
scans frozen attempts under trusted host roots. Configure `--runner-state`,
`--private-root`, `--agent-mount`, `--baseline-bundle` and its trusted
`--baseline-sha256`; none comes from an agent request. Its baseline must not
be inside the agent mount. It refuses ambient provider credential environment
variables and never loads a token or calls GitHub. Each verification uses the
existing pinned, network-disabled Docker object verifier, and a reserved
verification identity is never rerun. It rechecks the active run binding
afterward. `bundle_status` takes only a commit and stage attempt ID, checks
the exact live grant and verified immutable bytes, and returns a digest rather
than a host path or bundle. Polling status never schedules or retries work.
Status remains `unknown` for pending, failed or partial verification. The
agent must use its configured bounded wait and then report incomplete delivery,
not invent success or automatically create another attempt. The verifier's
own failure journal distinguishes pre-dispatch validation rejection from
unexpected uncertainty. The resolver checks the live binding even if a
worker died before rewriting a briefly verified outcome after a binding change.

The worker must be independently managed alongside host services. The
opt-in Windows task installer below provides that deployment path; no task
is installed automatically. Scripted-container capture and cleanup are
bounded evidence, not real-model delivery acceptance. An unknown verification is not
permission to automatically freeze another attempt. `pr_read` accepts only a
PR number bound by creation or
trusted approval and returns the displayed title/body/base/head for agent
inspection while the run is alive. Reviewed `issue_create` needs a trusted
reviewed-payload binding.
It refuses arbitrary REST writes, GraphQL, credential export and unsupported
commands. Local editing remains ordinary container activity. The mediation
JSON client is not itself a `git` or `gh` executable. In opt-in Git workspace
mode, native Git uses the installed remote helper and the supported partial
`gh` adapter is on PATH; see [exact command scope](mediated-agent-commands.md).
Body-file/stdin forms are supported, but broader issue/API-write/pagination,
formatting and full parity remain #100 work. An agent must not fall back to
ambient credentials.

| Requested surface | Current agent-stage result | Local evidence |
| --- | --- | --- |
| Edit files in `/draft` | Default snapshot has no history; opt-in Git workspace has isolated history | `test_local_runner.py` |
| Literal `git fetch` / `git push` | Scoped native remote helper; fetch requires explicit run/base reads, push requires verified exact commit | `test_native_commands.py`; S10 B local-provider and S12 B live scripted-container evidence |
| Normalized host `git_push` | Active capture, independent credential-free verification and trusted exact-commit transport | `test_bundle_verifier.py`, `test_verified_stage.py`, `test_github_git_transport.py`; S12 B live scripted-container evidence, not production LocalRunner acceptance |
| Literal `gh pr` / `gh run` | Supported partial create/view/edit and run-list forms; result JSON | `test_native_commands.py`; S10 B fake PR correction/readback and S12 B live PR create/readback |
| Literal `gh issue` | Unsupported before mediation; no implicit run permission | `test_native_commands.py`, `test_github_mediation.py` |
| Normalized PR create/update | Granted branch/PR/base/marker checks, with provider target verification | `test_github_mediation.py`, `test_github_rest_transport.py` |
| Bound PR readback | Granted PR number, repository, branch and base; title/body and actual head SHA returned | `test_github_mediation.py`, `test_github_rest_transport.py`; synthetic transport only |
| Normalized Actions read | Granted repository target only | `test_github_rest_transport.py`, no-model Docker client check |
| Reviewed issue create | Broker requires a trusted reviewed-payload binding; not granted to this agent runner | `test_github_mediation.py` |
| General `gh api` REST/GraphQL | Arbitrary writes and GraphQL denied; same-repository REST GET is diagnostic-only | `test_github_mediation.py`, `test_github_rest_transport.py` |
| Git timeout and late process | Host Git tree is bounded; uncertain push remains `unknown`; descendant cleanup has a synthetic control | `test_github_git_transport.py` |

This is a coverage inventory, **not** a #100 parity pass. In particular, no
literal `gh` or `git` command coverage can be inferred from the normalized
operation tests.

The no-model Docker test is opt-in:
`LAOMEDO_DOCKER_MEDIATION_TEST=1 python -m pytest
tests/test_agent_mediation_container.py`. It uses a synthetic run capability
and fake loopback mediator, never GitHub. Standard host tests cover service
composition, stale-instance refusal, and the read-only mount command.
The synthetic integrated runner test starts a real independent lease and
mediator process, checks an authorized launch and a stale-mediator refusal,
and verifies lease finish without a model or GitHub call. It does not replace
the frozen live runner-loss test.
## Windows managed startup (implementation draft)

`scripts/Install-LaomedoUserTask.ps1` registers one per-user task for
`host-services` and a separate task for `bundle-verifier`. Supply an absolute
Python executable, checkout and host-only JSON configuration file. Use
`-WhatIf` to inspect registration first. Registration does not start the task;
start the exact returned name only after reviewing its definition. Existing
names are refused rather than overwritten. Tasks use an interactive, limited
principal, logon trigger, IgnoreNew and three bounded restarts. Logout and
machine failure survival are not claimed. Configuration files belong outside
agent mounts; the verifier configuration cannot include a token reference.
The host configuration contains only explicitly selected token-file/key
references, never token values. Keep those files host-only and retain grant
expiry even if Task Scheduler itself fails. No production task has been
installed by default. The separately frozen task S1 diagnostic passed and
removed its two exact tasks; see `experiments/exp104/MANAGED-STARTUP-RESULTS.md`.
This does not establish production, logout or in-flight verifier cleanup.

Later [S12 B](../experiments/exp104/NATIVE-MANAGED-S12-B-RESULTS.md)
composed these exact per-user tasks with real native Git/PR operations,
independent revocation within 4.985 seconds and B-run continuity. Its workers
were scripted container fixtures, not production LocalRunner/model turns.
[S10 B](../experiments/exp100/S10-B-RESULTS.md) supplies the separate local
two-push and PR-body-correction checks. Neither proves full capability parity,
logout/double-manager survival, Linux or Q11 acceptance.

PR updates now require an `expected` snapshot containing `title`, `body` and
`head_sha`. The adapter compares a fresh GET before PATCH, verifies the bound
target, then checks another GET after PATCH. It refuses stale input before
writing and returns uncertainty on any failed/mismatching post-write readback.
The read/PATCH gap is not atomic; a concurrent edit can still be overwritten,
as accepted by the user. Never resend an unknown update automatically.

The verifier now reserves its exact Docker stage name, random ownership token
and pinned image before creating anything, while holding an OS file lock.
Subsequent worker scans can reconcile a claimed attempt only after that lock
is free. They check name/labels/image and recheck the ID before ID-only removal;
an absent or unavailable daemon is not proof of cleanup. A container appearing
late can be removed on a later scan, without redispatching verification. This
is local implementation with synthetic controls; real worker-loss cleanup
still requires a frozen independently reviewed diagnostic. The manager must
be alive or restart for this reconciliation; power loss and manager failure
are not safe-cleanup guarantees.

