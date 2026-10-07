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
reader cannot mistake a truncated renewal for a lost process. The two clock
values remain separate files; service-manager deployment and failure behavior
still need their own check.

The current Docker route uses `host.docker.internal` to reach a loopback-only
host mediator. A no-model test checks that route on Windows Docker Desktop.
The runner refuses mediated dispatch on other host platforms until their
container-to-loopback route is specified and tested. It also checks the
mediator's live instance identity before launching the container. The
credential-owning service is not started implicitly by an agent run.

## Current operation boundary

The mediator accepts normalized `git_push`, `pr_create`, `pr_update`,
`actions_read`, and a separately diagnostic `api_rest_read` when the grant
allows them. Reviewed `issue_create` needs a trusted reviewed-payload binding.
It refuses arbitrary REST writes, GraphQL, credential export and unsupported
commands. Local Git editing/committing remains ordinary container activity;
this client is **not** a drop-in `git` or `gh` executable. In particular,
literal `git fetch`, `gh pr`, `gh issue`, and general `gh api` parity, input
files/stdin flags, output formatting, and safe host-checkout commit transfer
remain #100 work. An agent must not fall back to ambient credentials.

The no-model Docker test is opt-in:
`LAOMEDO_DOCKER_MEDIATION_TEST=1 python -m pytest
tests/test_agent_mediation_container.py`. It uses a synthetic run capability
and fake loopback mediator, never GitHub. Standard host tests cover service
composition, stale-instance refusal, and the read-only mount command.
