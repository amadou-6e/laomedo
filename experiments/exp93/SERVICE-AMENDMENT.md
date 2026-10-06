# EXP-93 amendment 2: independent lease service under whole-tree kill

Frozen after the negative whole-tree diagnostic (`b61a630`) and after the
implementation commit that moves supervision into `laomedo.lease_service`.
This is a new, single-use, zero-model case with fresh identities. It is not a
retry of either earlier case.

## Question

When the runner's **entire process tree** is killed with `taskkill /T /F`, does
the independently started lease service (1) revoke the run-scoped external-write
grant and (2) remove only the exact owned container, both within the selected
60-second bound, while (3) an unrelated lookalike container survives?

## Setup

One fresh temporary root. The probe parent starts the lease service as its own
child, never as a descendant of the runner. It then starts one disposable runner
child. The child registers one lease (fresh run ID, exact name, launch token)
through the production `LeaseClient`, reads its grant, and starts one labelled
container from the pinned local `laomedo-codex-boundary:0.159.2` image with
`--pull=never`, `--cap-drop ALL`, `no-new-privileges`, a numeric user and the
two ownership labels. The container's only job is a loop that POSTs to the
service's synthetic `/write` endpoint through `host.docker.internal` with the
grant. The probe parent also starts one unowned sleeper whose name shares the
`laomedo-codex-` prefix but carries other labels.

## Procedure

1. Wait until the owned container is running, its labels match the lease, and
   the service has logged at least one **accepted** write for the grant.
2. Verify the runner child's and service's exact PIDs and command lines.
3. Kill the runner child once with `taskkill /PID <child> /T /F`.
4. For up to 60 seconds, watch for the service's lease result and for the owned
   container's absence by exact name and labels.
5. Re-use the grant from the probe parent once after the result appears.

## Pass criteria

All of the following, measured from the kill:
- the service process is still running and its heartbeat is fresh;
- the lease result is `heartbeat_lost`, names the grant as revoked, and reports
  `cleanup_verified: true`;
- revocation time and owned-container absence are each under 60 seconds;
- the service logged **no accepted write after revocation**, and the parent's
  post-revocation write returns 403;
- the lookalike container is still running;
- zero model turns, no GitHub token and no real credential.

The machine observation is written once; an existing observation refuses a
rerun. Afterwards the probe may remove only its two exact containers (name and
labels checked) and stop only the exact service PID.

## Limits

A pass shows the lease service sits outside the runner's Windows process tree
for this kill and enforces revocation of its own synthetic grant. It does not
test a systemd cgroup or Windows job-object stop that includes the service,
power loss, a real push credential, a copied credential outside the grant
broker, or a Codex agent. If the service itself dies, the synthetic grant
endpoint disappears with it, but container cleanup then waits for the runner's
startup sweep; that double-failure path is not tested here.
