# Mediated agent host services (staged, Windows local slice)

The agent runner can now pass a run-scoped mediator capability to its pinned
Docker image. The reusable GitHub credential remains in a host-only service.
This is **not** acceptance of #100 capability parity or #104's live runner-loss
gate. No live GitHub write is part of this setup check.

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
`actions_read`, and a separately diagnostic `api_rest_read` when the grant
allows them. **The current agent runner refuses a `git_push` authorization**:
its `/draft` snapshot has no Git history and cannot supply a commit to the
mediator's fixed trusted checkout. Agent-stage grants are limited to Actions
reads and approved PR create/update for branches prepared outside the stage.
Reviewed `issue_create` needs a trusted reviewed-payload binding.
It refuses arbitrary REST writes, GraphQL, credential export and unsupported
commands. Local editing remains ordinary container activity, but this copied
`/draft` workspace has no Git history, so it cannot create a pushable commit;
this client is **not** a drop-in `git` or `gh` executable. In particular,
literal `git fetch`, `gh pr`, `gh issue`, and general `gh api` parity, input
files/stdin flags, output formatting, and safe host-checkout commit transfer
remain #100 work. An agent must not fall back to ambient credentials.

| Requested surface | Current agent-stage result | Local evidence |
| --- | --- | --- |
| Edit files in `/draft` | Works; no `.git` history is copied | `test_local_runner.py` |
| Literal `git fetch` / `git push` | Unsupported; no agent-side Git transport or transferable commit | `test_local_runner.py` rejects `git_push` grants |
| Normalized host `git_push` | Broker can push a verified host commit, but not one made inside the agent snapshot | `test_github_git_transport.py` |
| Literal `gh pr` / `gh issue` / `gh run` | Unsupported; no CLI-compatible adapter yet | Client accepts JSON only; unsupported operations fail in `test_github_mediation.py` |
| Normalized PR create/update | Granted branch/PR/base/marker checks, with provider target verification | `test_github_mediation.py`, `test_github_rest_transport.py` |
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
