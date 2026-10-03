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

`runner_probe_sidecar.py` contains the proposed fixed unauthenticated runner
API request for a later internal-network stage check. Its route, status-only
response and rejection of stage-controlled paths or bodies are unit tested.
The sidecar has not been deployed or connected to the runner.

No E05 Docker stage or agent turn has been launched. Starting a stage in steps
3-6 still requires review of the amended protocol and verifier. These
create-only refusals do not establish a Docker write boundary or an
agent-originated denial. They do not relax the current runner's permissions.
