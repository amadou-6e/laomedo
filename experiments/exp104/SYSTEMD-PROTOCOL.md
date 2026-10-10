# S14: disposable Linux service-manager boundary, synthetic

Issue #104, related #100. Governing specs main
`5a8fbc9c248bb263f57bdc4fb5f2bb3023c55810`. User explicitly approved a
temporary privileged systemd Docker container on 2026-10-10, without WSL
configuration changes or a claim of full Linux runner support. Freeze this
protocol before fixture implementation or acceptance execution.

## Question and scope

Can real systemd put a lease/mediator service outside two runner cgroups, kill
all processes in runner A's cgroup, and keep the production grant boundary
denying A within60seconds while runner B and the service remain usable?
Exercise production MediationStore, RunGrantAuthority, LeaseService and
LeaseClient with a synthetic provider. No GitHub identity/token, model turn,
Docker socket mount, host PID/network/cgroup namespace, host filesystem bind
or persistent unit/WSL change. A privileged container still has increased
access to the Docker VM; run only pinned trusted fixture code, network-none,
private cgroup namespace, bounded resources and an exact owned container.

## Frozen cases and interpretation

1. Read back systemd version, PID1, unit MainPID/ControlGroup/KillMode/Restart
   properties and process membership. Service, runner A and runner B must be
   in distinct nonempty cgroups. Each runner starts a child, whose membership
   is checked. Save actual durable grant/lease identities, never bearers.
2. A and B each perform a synthetic granted mutation and provider counts
   reflect it. Repeating a confirmed identity does not dispatch again.
3. `systemctl kill --kill-who=all --signal=KILL` targets only runner A's unit.
   Record monotonic kill start/completion and independently inspect parent
   and child disappearance. Do not infer tree loss from a stopped main PID.
4. Keep A's exact capability in the controller. Wait boundedly for the real
   lease result. A's post-loss request must be denied, grant revocation must
   be<=60s after kill completion, and provider counts must not increase.
   B performs an independently identified authorized update after A denial;
   it must reach the synthetic provider. Service/B MainPID must be unchanged.
5. Restart the lease/mediator service unit. Its instance and MainPID must
   change, and retained old B capability must be denied without provider
   dispatch. Old lease must not be silently adopted. Check expired/revoked
   renewal refusal using production store paths; synthetic expiry control is
   separately labelled, not a claim of a production wall-clock failure.
6. Unknown write and changed-payload controls use a synthetic lost response
   and actual durable effect journal: same identity never redispatches;
   changed content conflicts. Controls never introduce a real external effect.

Cleanup callback is explicitly synthetic: no inner stage Docker container
exists. Its result must not claim verified container cleanup. Existing Windows
S13 supplies separate exact-container/live-GitHub evidence; this test adds
only Linux service-manager/cgroup and synthetic grant behavior.

## Prospective capture and controls

Fresh one-shot identity `exp104-systemd-s14-20261010-a`. Pin exact source,
image ID, protocol commit, unit bytes and independent pre-run approval before
dispatch. Claim identity with exclusive local directory creation; any failure
consumes it. Use a temporary owned container name/label, image ID check and
ID-only rechecked removal. Do not remove unrelated containers or volumes.
Runtime limit240s, Docker commands30s, service readiness30s, revocation60s,
final cleanup30s. No automatic experiment replay; setup failure is retained
as incomplete evidence, not quietly retried. Image building/pulling is setup,
not evidence of systemd behavior. No broader cgroup/host mount is permitted
as an undocumented workaround for a failed boot.

Machine observation keeps stage/status, times, sanitized provider attempts,
actual units/PIDs/cgroups and cleanup. Preserve originals with LF bytes and
hash committed files. A checker must reject fake success after removal of
the post-loss denial, B continuity, child kill, grant identity, restart denial
or distinct-cgroup evidence. Tests/probe development do not count as campaign
evidence. Record limitations and independently review before issue closure.

Primary references: [systemd cgroup delegation](https://github.com/systemd/systemd/blob/main/docs/CGROUP_DELEGATION.md)
and [Docker run namespaces/privileges](https://docs.docker.com/reference/cli/docker/container/run/).
No production Linux container routing, GitHub writes on Linux, logout,
double-manager survival, Q11, credential isolation against privileged hostile
code or full CLI parity is inferred.
