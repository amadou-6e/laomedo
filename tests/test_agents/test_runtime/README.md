# Runtime controls

The suite protects Agent lifecycle, request identity, startup/recovery, accounting,
command completion and failure finalization. Internal transports are doubles; these
checks do not establish real provider or graph acceptance.

`test_docker.py` protects shared client ownership, detached endpoint overrides,
exact receipt-service selection and propagation of native cleanup uncertainty.
It patches only the Docker client boundary and never contacts a daemon.

`RunnerCase` in `models.py` owns one temporary source, imported Skill receipt and
CodexAgent. `create()` prepares fresh resources and cleans partial setup on failure;
`request()` produces a fresh request bound to that receipt; `close()` releases only
its owned resources. Runtime handles are excluded from model serialization.
`prepare_runner()` binds that case to existing tests without borrowing a TestCase.
`transport.py` defines the shared internal ACP transport. `commands.py` specializes
it at module scope for command events, uncertain cleanup and resumed commands.
`test_commands.py` preserves the dangling-command, terminal status, artifact gating,
redaction, cleanup uncertainty and stale-snapshot assertions across the ACP move.

Run `python -m unittest discover -s tests/test_agents -t tests -v` with the declared
runner dependencies. No campaign, model turn or experiment checkout is required.

Preparation/status compatibility uses data/prepared-records.json and the existing owned RunnerCase; only a random private Git hooksPath hash is recomputed. These are internal compatibility fixtures, not real provider acceptance.

## Real Docker acceptance without model execution

`test_docker_integration.py` is opt-in. Set `LAOMEDO_TEST_DOCKER_IMAGE` to an
already installed image with `/bin/sh` and run
`python -m unittest tests.test_agents.test_runtime.test_docker_integration -v`
with `PYTHONPATH=src;tests` and the runner dependencies installed.
It overrides the image entrypoint, uses no network or mounts, and runs as
10001:10001 with a read-only root. It checks job output/exit/removal, interactive
I/O, in-container exec, repeated close and receipt recovery through
`laomedo.docker.DockerRuntime`. It never starts the image's ordinary service or
an AI agent. These checks establish Docker mechanics, not native-agent acceptance.
