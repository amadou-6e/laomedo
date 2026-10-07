# #107 Codex subscription connection boundary probe

Observed on 2026-10-07 against Laomedo `c93be20`, Docker Desktop Engine
27.3.1, and the pinned `laomedo-codex-boundary:0.159.2` image. This is a
credential-free check of the existing controller and command layout, not a
Sign in with ChatGPT connection or a model-backed run.

## Question and method

The proposed [authentication contract](https://github.com/amadou-6e/specs/blob/1da03b5/projects/laomedo/subsystems/agent-execution/contract/authentication.md)
would give Codex app-server an OAuth access token in `ACCESS_TOKEN`, as in the
[OpenAI app-server recipe](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server).
Can a command invoked through this runner's `command/exec` read that token?

Run the probe from the Laomedo checkout in PowerShell:

```powershell
$env:PYTHONPATH = (Get-Location).Path
python experiments/feasibility/107/probe_controller_env.py
```

The probe constructs the reviewed Docker command, replaces the
real Codex login volume with disposable tmpfs, and gives app-server a random
synthetic canary in `ACCESS_TOKEN`. It initializes app-server, then makes three
`command/exec` calls that test for the variable without printing its value.
The temporary event log is removed when the probe exits. No browser, real
credential, model turn, or persistent Docker volume is used.

| Access route from `command/exec` | Exit code | Observation |
| --- | ---: | --- |
| Command environment: `ACCESS_TOKEN` is set | 0 | Readable |
| Controller `/proc/1/environ` contains `ACCESS_TOKEN` | 0 | Readable |
| Command's own `/proc/self/environ` contains `ACCESS_TOKEN` | 1 | Not observed there |

The probe returned `controller_env_credential_route_safe: false` and
`model_turns: 0`. A follow-up `docker ps -a` check found no named probe
container left behind. The command-environment result alone is a positive
secret-access path. The `/proc/1/environ` result supplies an independent path.
The `/proc/self/environ` negative result does not make the boundary safe.

## Decision and limits

**No-go for passing a reusable subscription access token through the current
single-container controller environment when untrusted commands are enabled.**
Do not wire Sign in with ChatGPT tokens into this runner or call its present
`command/exec` boundary credential-safe. A clean environment assertion, a
prompt rule, or output redaction cannot undo an observed read path.

This says nothing about whether the selected account will grant ChatGPT plan
usage. OpenAI's [local-app guide](https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt)
lists personal projects that run locally as eligible in principle; Laomedo has
not performed app-owned sign-in or checked this account's granted scopes.
Refresh, restart, sign-out, and account switching are also untested. No
production credential broker was added here.

The next implementation needs a controller/tool separation that denies both
environment and controller-process reads, followed by canary probes through
every command and bundled-script path. Only after those denials should #107
connect an account, implement its persistent refresh lifecycle, and request a
separately capped live test. The existing copied-login prototype remains
unchanged; this experiment does not upgrade its security claim.

## Split controller and executor follow-up

The pinned image also provides a local app-server `environment/add` connection
to `codex exec-server`. The follow-up uses a credential-free fake Responses
stream to request a real `functions.exec` call. It makes no OpenAI request and
uses zero model turns. The controller has a synthetic `ACCESS_TOKEN` in its
environment and a canary file in its private Codex home. The executor has no
token, no canary file, and no login volume. The two containers
share a Docker network namespace for loopback transport, but have separate PID
and mount namespaces. Their only shared file mount is the disposable draft.

Run from the Laomedo checkout:

```powershell
$env:PYTHONPATH = (Get-Location).Path
python experiments/feasibility/107/probe_remote_executor.py
python experiments/feasibility/107/probe_remote_executor.py --disconnect-executor
python experiments/feasibility/107/probe_remote_executor.py --patch-probe executor
python experiments/feasibility/107/probe_remote_executor.py --patch-probe controller
```

The controller enables `deferred_executor` and
`executor_capability_discovery`, selects the registered environment on both
`thread/start` and `turn/start`, and uses `externalSandbox` for the turn. The
combined configuration passed; individual flag necessity was not tested.
Without the turn-level configuration, a synthetic
agent command ran in the controller and read the canary despite a successful
`environment/status: ready` result. This is a measured silent fallback, not
proof that environment registration alone isolates commands. A similar
host-local fallback was [reported upstream](https://github.com/openai/codex/issues/41563)
for an older Codex build.

With those selections, the fake model's command executed in the remote
executor. Both an inline command and a bundled shell script checked their own
environment and `/proc/1/environ`; the script also checked the private canary
file. All five agent-path checks returned `absent`. Independent direct
executor checks returned `absent` for the environment, process, and file
routes. The
app-server event stream contained one `commandExecution` completion with exit
code 0, and the draft marker was present. The probe reports
`agent_command_boundary_verified: true` and
`controller_token_absent_from_executor: true` for this exact command path.

In the negative control, the executor was removed before `turn/start`. The
turn timed out, no command event or marker appeared, and the controller did
not run the command during the observation window. This supports a fail-closed
result for that failure point only; it does not establish recovery or a
general liveness bound. Both probe variants removed their disposable
containers. The fake backend and synthetic canary used no personal login,
browser authorization, or model turn.

The `apply_patch` control changed an executor-only file and left a
controller-only file untouched. The controller-only attempt returned a
file-not-found error from the tool, while a host-side check confirmed that
file still held its original bytes. The successful executor-only control is
needed because an absent file alone would not prove which process handled
the patch. These probes cover update hunks only; they do not prove all patch
operations or other native tools route to the executor.

This is a promising **experimental route**, not yet a production connection.
It has not tested every tool or filesystem operation, broker IPC, access to a
real token store, refresh rotation, resumed threads, or restart. It also has
not established that this account can grant Sign in with ChatGPT plan usage.
The current runner still uses its original single-container transport; do not
inject a reusable subscription token into it. #107 remains open until the
split is implemented in that transport, broader access paths are denied, and
the separately authorized live and restart checks pass.

## Proposed runner integration, pending review

The next code slice should keep the existing runner route unchanged until the
new one passes a startup gate. For each run, launch an executor container with
only the draft workspace mount and a disposable, nonsecret Codex home. Launch
the app-server controller in a separate PID and mount namespace. Only the
controller may receive a provider credential or persistent auth state. Use
the executor's loopback, capability-authenticated exec-server connection for
the controller-to-tool channel; never mount the Docker socket in either
container.

After `initialize`, register the executor and require a ready status and
expected shell information. Configure the controller with the two observed
executor feature flags. Select the exact environment on every thread start or
resume and on every turn, with `externalSandbox` on the turn. Refuse dispatch
if any selection is missing, mismatched, or rejected. Do not use the current
controller-local `command/exec` preflight in this mode: run boundary probes
against the executor and require a real agent-issued command check before a
credential is connected. Treat executor loss as a failed or unknown turn;
never retry locally. On shutdown, verify removal of both owned containers.

This is a draft launch shape, not an applied runner configuration. Review must
settle the exact Docker mounts, network policy, status evidence, and resume
behavior before enabling it. The later credential connection needs its own
eligibility, refresh, and restart checks under #107.
