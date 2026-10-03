# EXP-18: Docker stage protection preflight

This directory prepares the [E05 protocol draft](https://github.com/amadou-6e/specs/pull/195).
`preflight.py` compares a created container's effective Docker inspect fields
with a preapproved mount and protection manifest. It refuses extra capabilities,
security options, namespaces, devices, tmpfs mounts, and image-ID changes as
well as missing required protection. Unit tests cover each of the eight real
Docker downgrades reported in the PR review.

`python experiments/exp18/probe_create_only.py` runs only approved protocol
steps 1-2: validate private fixture roots, create and inspect a correct
container without starting it, refuse a writable `/skills` bind, and confirm
an unavailable seccomp profile fails at `docker create`. The 2026-10-03
observation passed with zero stage starts, dispatch attempts and model turns;
named Docker resources were removed. See `create-only-observation.json`.

No E05 Docker stage or agent turn has been launched. Starting a stage in steps
3-6 still requires review of the amended protocol and verifier. These
create-only refusals do not establish a Docker write boundary or an
agent-originated denial. They do not relax the current runner's permissions.
