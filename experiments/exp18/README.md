# EXP-18: Docker stage protection preflight

This directory prepares the [E05 protocol draft](https://github.com/amadou-6e/specs/pull/195).
`preflight.py` compares a created container's full normalized `HostConfig`
against `hostconfig-27.3.1.json`, a sanitized baseline from the pinned image
and Docker Desktop 27.3.1. Only the per-run network and two bind sources are
normalized. It also checks the image ID, user and top-level mount sources,
read/write modes and propagation. The real `systempaths=unconfined` shape
changes `MaskedPaths` and `ReadonlyPaths`; tests cover that and each other
reviewed downgrade. Unknown `HostConfig` fields fail closed.

`python experiments/exp18/probe_create_only.py` runs only approved protocol
steps 1-2: validate private fixture roots, create and inspect a correct
container without starting it, refuse a writable `/skills` bind, and confirm
an unavailable seccomp profile fails at `docker create`. The 2026-10-03
observation passed with zero stage starts, dispatch attempts and model turns;
named Docker resources were removed. See `create-only-observation.json`.

`runner_probe_sidecar.py` contains the fixed unauthenticated runner
API request for the internal-network stage check. Its route, status-only
response and rejection of stage-controlled paths or bodies are unit tested.
For the approved no-model steps 3-4, `Dockerfile.sidecar` builds it from a
pinned local Python image. `probe_stage.py` verifies its pinned image ID,
exactly two networks, zero mounts and published ports, read-only root, dropped
capabilities, `no-new-privileges`, non-root user and fixed command before
starting the stage. The sidecar then reaches a disposable local runner on port
8767 with model turns disabled. `Dockerfile.canary` packages the EXP-07 grant
canary from the same pinned base image.

The approved [direct no-model observation](stage-observation.json) records a
stage that wrote its disposable checkout and scoped HTTP canary, read its
effective skill, received `EROFS` on a skill write, found no protected marker
in a complete bounded sweep, failed to reach host listeners directly, and
cleaned up. The host snapshot hash rejected the stage-created symlink. Two
earlier runs were inconclusive because the initial marker sweep skipped large
image files; the final streaming sweep covered those files. No model turn or
personal credential was used. This is a direct process-boundary result, not
the agent-originated criterion or a production runner integration. The
current runner's permissions remain unchanged.
