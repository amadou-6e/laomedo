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
usage. OpenAI's [quickstart](https://developers.openai.com/siwc/quickstart),
checked on 2026-10-07, says plan usage is available to open-source partners
and selected private clients. Laomedo has not established selected-private-client
access or performed app-owned sign-in with separately granted Responses API
scopes.
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
python experiments/feasibility/107/probe_remote_executor.py --listener-probe
python experiments/feasibility/107/probe_remote_executor.py --restart-probe
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

In the revised negative control, the executor was removed after the fake
model request began, while the turn was active. The five-second wait ended as
`timeout` about 4.5 seconds after removal. No command event or marker appeared,
and the controller did not run the command during that window. This supports
an `unknown` outcome for this loss point, not a general recovery or liveness
guarantee. All probe variants removed their disposable containers. The fake
backend and synthetic canary used no personal login, browser authorization,
or model turn.

The `apply_patch` control changed an executor-only file and left a
controller-only file untouched. The controller-only attempt returned a
file-not-found error from the tool, while a host-side check confirmed that
file still held its original bytes. The successful executor-only control is
needed because an absent file alone would not prove which process handled
the patch. These probes cover update hunks only; they do not prove all patch
operations or other native tools route to the executor.

The reviewer independently exercised code-mode JavaScript and `view_image`
against the same fake backend. The JavaScript had no direct `process`, `Deno`,
`require`, or `fetch` access, and `view_image` resolved executor-only and
controller-only paths from the executor side. Their [review of this
draft](https://github.com/amadou-6e/laomedo/pull/109) records the exact
observations. The follow-up probe pins the image digest and `codex-cli
0.159.2`, and reads `ALL_TOOLS` from inside a synthetic `functions.exec` call.
The observed code-mode inventory matches the reviewed nine names exactly:
`apply_patch`, `clock__curr_time`, `create_goal`, `exec_command`, `get_goal`,
`update_goal`, `view_image`, `wait_for_environment`, and `write_stdin`. An
unexpected tool makes the normal probe fail.

The controller listener gate matches listening TCP and Unix socket inodes to
processes in the controller PID namespace. At startup it found none. A
negative control started a loopback exec-server listener and an abstract Unix
listener in the controller. The gate detected both as `tcp` and `unix`,
matched the injected abstract socket by name and owned inode, and returned a
refusal when called with those listeners present. The probe did not submit a
turn after injection. Filesystem-path Unix and IPv6 TCP listeners were not
injected, and this gate does not check UDP sockets. Because the two containers
still share a network namespace, production integration must either use
separate network namespaces or close these detection gaps and run the gate
before each dispatch.

The `commandExecution` item in the pinned app-server event has no explicit
environment ID. Exact thread and turn selections plus the canary result give
evidence for this probe, but the event by itself cannot attest that a future
turn ran in the executor. Production dispatch still needs a tested per-turn
routing check; a mere `environment/status: ready` result is insufficient.

This is a promising **experimental route**, not yet a production connection.
It has not tested every tool or filesystem operation, broker IPC, access to a
real token store, refresh rotation, a full runner restart, or a live model
turn. It also has not established that this account can grant Sign in with
ChatGPT plan usage.
The current runner still uses its original single-container transport; do not
inject a reusable subscription token into it. #107 remains open until the
split is implemented in that transport, broader access paths are denied, and
the separately authorized live turn and full runner restart checks pass.

## Controller restart and native resume follow-up

On 2026-10-07, `--restart-probe` kept the same remote executor and workspace
while replacing the app-server controller. It used a newly created Docker
volume only for that controller's synthetic Codex home, never the real login
volume. A named, one-time network-disabled init container set that disposable
volume to UID/GID 10001; an unprepared Docker volume was root-owned and caused the
non-root app-server to exit before `initialize`.

The first synthetic turn completed. After controller removal, the new
app-server found no controller listener at startup, registered the same
executor and found it ready, resumed the original native thread ID, and
completed a second synthetic turn. The second turn issued a fresh agent command:
its workspace
marker and all five environment/process/file checks were written after the
first turn's files were removed. Every check reported `absent` for the
controller canary. The second turn's tool output independently matched the
exact nine-tool surface, and its request retained the first turn's tool-output
history. The fake Responses server received exactly four requests across the
two turns. The image ID and CLI version matched the pinned values. Only the
local fake Responses backend was configured; no real account, browser login,
or persistent credential was used. The ordinary probe still passed, all 192
host tests passed (4 skipped), and no named probe container or
disposable controller volume remained.

This establishes a credential-free `thread/resume` route after **controller**
replacement, with retained tool-output history and remote tool execution
observed on the resumed turn. It does not establish broker refresh, real
account eligibility, a full runner restart,
or safe fallback behavior for all future Codex versions and tools. The
`commandExecution` event still has no environment ID, and the containers
still share a network namespace. The production runner remains unchanged.

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
expected shell information. Reject a controller with any listening TCP or
Unix socket, including abstract Unix listeners, and repeat that check before
each turn while the network namespace is shared. UDP remains outside this
gate, so a shared network namespace cannot be called fully isolated on this
evidence. Gate on the exact pinned
image, CLI version, and nine-tool code-mode inventory; any tool addition needs
new access-path tests. Configure the controller with the two observed
executor feature flags. Select the exact environment on every thread start or
resume and on every turn, with `externalSandbox` on the turn. Refuse dispatch
if any selection is missing, mismatched, or rejected. Do not use the current
controller-local `command/exec` preflight in this mode: run boundary probes
against the executor and require a real agent-issued command check before a
credential is connected. Establish a per-turn executor-origin check beyond
the current event fields. Treat executor loss as an unknown turn within a
short tested bound; never retry locally. On shutdown, verify removal of both
owned containers.

This is a draft launch shape, not an applied runner configuration. Review must
settle the exact Docker mounts, network policy, status evidence, and resume
behavior before enabling it. The later credential connection needs its own
eligibility, refresh, and restart checks under #107.
