# Claude subscription controller

Install the host runner's OTLP dependencies from the repository root:

```powershell
python -m pip install ".[observability]"
```

The controller exports native metrics, events and beta traces to a private local
receiver. This host dependency is separate from the Docker image. Prompt and tool
content export stays off; exporter credentials never reach command workers. Missing
receiver dependencies refuse the controller turn before model dispatch.

Build from the repository root:

```powershell
docker build -t laomedo-claude-controller:2.1.310 docker/claude
docker volume create --label laomedo.provider=claude laomedo-claude-profile
docker run --rm -it --mount type=volume,source=laomedo-claude-profile,target=/profile laomedo-claude-controller:2.1.310 auth login
```

Use a separate subscription login or an explicitly authorized login-only local
migration. Do not mount a personal profile, copy personal sessions, forward API
billing keys, or put credentials in source, graphs or logs. Avoid concurrent
credential refreshes from duplicate logins. For an opted-in single-user local
runner, managed startup can set `mirror_host_claude_login: true`. The host mirrors
only its current access credential before authentication checks; the rotating
refresh credential is never copied. Refresh or sign in on the host when its access
credential expires. Remote Docker endpoints are refused for this mirror. The volume retains the native
sessions required for Resume; deleting it invalidates those sessions.

Start an independent `laomedo.host.leases.service_cli` for exact ownership/heartbeat cleanup
before the API. Supply its private state directory using `--lease-service`.
The API must not own the only cleanup process. The image is resolved to its
immutable Docker ID and checked against the supported CLI version at startup.

The networked controller owns only its dedicated subscription profile. Native
controller file and shell tools are disabled; draft reads and edits use the
credential-free command worker. The MCP command capability dispatches
commands into a separate container with no network and no credential volume.
Host-mediated GitHub tools are offered only with a frozen authorization scope.
Shell-capable skill preprocessing and permission overrides are rejected before
native dispatch. Do not replace this boundary with an unrestricted Bash tool.

The controller and workers have read-only roots, dropped capabilities,
no-new-privileges and bounded process/memory/CPU resources. Exact owned-container
removal is verified before cancellation can be called confirmed. This is not a
claim that a container with provider credentials is an untrusted-code sandbox.

The managed recovery service must be deployed with the matching Docker runner
CLI: `--image`, `--profile-volume`, `--lease-service`, `--turn-timeout`.
Legacy `--executable` and verification `--max-model-turns` are not runner options.
Recovery UI PR #183 is integrated from develop; validate the combined stack before
release; independently deploying mismatched startup arguments is unsupported.

Controller and command-worker execution have an in-container deadline with a
five-second forced-stop grace period. An unverified owner is never signalled done: the
independent supervisor retains its loss-cleanup role. Unknown cleanup still fails
closed and must be reconciled before replacement work.

Native OTLP capture currently targets local Docker Desktop: the controller reaches
the loopback receiver through `host.docker.internal`. Native Linux Docker routing
is not established by the Windows integration evidence.
