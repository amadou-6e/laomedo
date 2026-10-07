# #107 Codex subscription connection boundary probe

**Current result (2026-10-07):** The app-owned split runner passed a bounded
single-user local live check before and after runner-process restart. The
original single-container no-go below remains valid for that old route; the
later split-route correction and [live observation](live-route-observation.json)
supersede it for the pinned local route. Refresh rotation, provider
revocation, host reboot and hosted isolation are still unproven.

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
usage. OpenAI's [local-project
guide](https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt),
checked on 2026-10-07, explicitly includes personal projects that run locally.
The [quickstart](https://developers.openai.com/siwc/quickstart) summarizes
availability more narrowly. A private, local Laomedo installation can try the
app-owned flow, but eligibility and the required plan-usage scope remain to be
verified by real consent and inference.
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

At this credential-free probe stage, this was a promising **experimental
route**, not a production connection. It had not tested every tool or
filesystem operation, broker IPC, access to a real token store, refresh
rotation, a full runner restart, or a live model turn. It had not established
that this account could grant Sign in with ChatGPT plan usage. The runner then
still used its original single-container transport; a reusable subscription
token must not be injected into that transport. The later opt-in split runner
and bounded live result are recorded below. #107 remains open for its broader
credential lifecycle and access-path acceptance checks.

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

## Opt-in runner integration and synthetic app-owned connection

The `feat/107` implementation adds an opt-in `--split-executor` mode. It keeps
a private controller profile in a Docker volume derived from the runner state
path, starts a separate disposable tool executor, checks both image IDs and
the controller's pinned CLI version, refuses controller-owned listening
TCP/Unix or UDP sockets before a turn, requires a ready remote executor, and
selects that executor on `thread/start` and `turn/start` with `externalSandbox`.
The original single-container route remains the default. `--auth-store`
selects a private app-owned OAuth store outside Git. It never imports the
user's Codex login file. A missing connection records `auth_missing` before a
model turn is reserved.

Run the credential-free product-route probe from the Laomedo checkout:

```powershell
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe experiments/feasibility/107/probe_runner_split.py
```

At the reviewed `6f14d12` revision, the fake Responses backend requested
three actual agent commands: first start, native resume in the same
`LocalRunner`, and a new run after reconstruction. That revision used a
synthetic app-owned account and showed that the old run refused resume after
runner restart while the new run completed without sign-in. Its agent commands
reported the controller token absent from their own environment,
`/proc/1/environ`, and a controller-only file path. The exact nine-tool
code-mode inventory matched the pinned list. Six fake Responses requests and
zero real model turns were used. This was a narrow positive result; the patch
route finding below changes the isolation verdict.

The access token is set in the controller container's environment and is
therefore visible to a host process with Docker Engine access through Docker
metadata while that controller exists. Docker access is part of the trusted
single-user host boundary; the executor receives no Docker socket. Per-turn
app-server events do not identify the executor, so exact routing is supported
by the pinned request shape and canary probes, not native event attestation.
The exact tool list is verified by the synthetic probe, not by a live startup
RPC. The containers share a network namespace, guarded by a controller-listener
check; this does not prove isolation against every network or IPC path. Do not
call this mode hosted or multi-user safe.

The OAuth broker follows OpenAI's dynamic registration, PKCE, ID-token
verification, scope checks, persistent host ID, single-writer rotating refresh,
and sign-out flow. Its tests use only synthetic tokens. A refresh is marked
uncertain before the request is sent, so an ambiguous response or crash cannot
silently replay the old refresh token. A different account cannot resume the
same run. A backend restart permits a new run, not automatic continuation of
the old one. At that synthetic-probe stage, browser consent, renewal with
OpenAI, actual plan entitlement, and bounded live before/after-restart turns
were untested; the later bounded live result is recorded below. One local browser
connection attempt on 2026-10-07 timed out waiting for the loopback callback;
the private store still reported `auth_account_missing`. This consumed no
model turn and does not establish an eligibility refusal. Two later callbacks
reached the app. The first exchange returned the old combined
`auth_network_or_exchange_failed` category; the second returned
`auth_transport_failed`, with no provider HTTP status. A credential-free Python
request to OpenAI's public discovery endpoint reported
`SSLCertVerificationError`, while Windows curl verified that endpoint and got
HTTP 200. This supports a Python TLS trust-path cause for the exchange failures,
but the first attempt's exact cause is unknown. The store remained unconnected;
no model turn was used. A separate credential-free Node HTTPS request inside
the pinned Codex controller image returned HTTP 401 from
`https://api.openai.com/v1/models`, which shows that image completed TLS for
that public endpoint. The expected unauthenticated response does not test
model access or the eventual access-token route.

## Bounded app-owned live check

With the pinned `truststore==0.10.4` dependency, the broker used an explicit
OS-native TLS context for token exchange, OpenID discovery, key-set lookup,
refresh and revocation. Hostname and certificate verification stayed enabled,
with TLS 1.2 as the minimum. A credential-free discovery request then returned
the expected OpenAI issuer, and browser consent created one active app-owned
connection. No existing Codex login file was copied.

The authenticated split-runner preflight reported `ready`, included
`gpt-6-luna` at `low` effort, and observed workspace write allowed, canonical
and sibling-store writes denied, and the controller-auth file absent from the
executor. It reserved no
model turn. Two subsequent **real** `gpt-6-luna`/`low` turns used a pinned
`live-107` skill. Each completed with the skill-only marker as its answer and
as the contents of a workspace file. Each private trace recorded a completed
`SKILL.md` read and marker-file command with exit code zero. The first run
completed as ledger attempt 1; the Python runner process then exited. A new
`LocalRunner` process used the same nonsecret credential reference without
browser sign-in and completed attempt 2 in a new native thread and workspace.
The private ledger is **2/2**, with both runs `completed` and no error category.

A host-side audit found neither the access nor refresh token in the private
run files or archived controller profile volume. No disposable split containers
remained. Raw traces and credentials stay outside Git. The active account is
still in the private persistent broker store, and the dedicated controller
profile volume persists for future authorized work. This proves the bounded
local before/after-process-restart route, not refresh rotation, sign-out,
host reboot recovery, network namespace separation or hosted isolation.

## Patch-route correction and bounded app-owned dispatch

The earlier `a0f9013` and `c1ef8ea` findings reported that an unselected
`apply_patch` wrote to the credential controller. That conclusion was wrong.
The check searched a tar archive of the entire controller profile for the
random marker. Codex also saves the tool-call input in that profile, so the
archive contained the marker even when the patch wrote elsewhere. The
historical result and its temporary fail-closed gate remain linked in the
specification as superseded evidence.

The corrected `probe_patch_route.py` reads the exact target file through a
separate read-only mount of the controller profile. It first confirms that a
host-created control file is visible through that mount, so a missing patch
file is meaningful. With the active runner configuration and a fake Responses
backend, the agent-originated patch completed in the executor: its file was
present in the live executor and absent in the controller. The disposable
`probe_patch_hook.py` variant produced the same result, without observed hook
feedback; the hook is not needed and is not active. The full
`probe_runner_split.py` exercises the app-owned `auth_store` path with a
synthetic broker account, redirects only that disposable runner instance to
the fake Responses backend, and checks the controller file exactly after
three synthetic turns. It retains the controller canary checks. All probes
used a dummy token, removed disposable containers and volumes, and used zero
model turns. The new four-turn cap remains **0/4 used** at this correction
point. The separate programmatic `split_access_token` path is only for
synthetic probes and must never carry a real credential.

A later credential-free rerun deleted the first disposable workspace after
same-runner resume, then reconstructed the runner and completed a new run
with the same synthetic broker reference. The probe verifies its resolved
delete target stays inside its temporary directory. This covers workspace
disposal for the local prototype without deleting any real run evidence or
spending another model turn.

Pinned Codex 0.159.2 resolves an `apply_patch` without an Environment ID to
the turn's primary environment. The runner supplies exactly one registered
executor environment on thread start, thread resume, and turn start, and now
refuses a missing, ambiguous, or mismatched selection before dispatch. The
earlier negative control showed why turn-level selection matters: omitting it
sent a shell command to the controller. This result supports a bounded
single-user local continuation, subject to final review and live canaries.
It does not prove every future Codex version, legacy default routing, native
per-event executor attestation, independent network namespaces, or hosted
isolation. Trusted host Docker users can still inspect a running controller's
token. Actual provider refresh, revocation, and host reboot remain untested.

## Live route recheck after the correction

After specs #269 and Laomedo #112 merged, the existing app-owned ChatGPT
connection passed a model-free preflight with `gpt-6-luna` at `low` effort.
No browser sign-in or credential copy was needed. The operator had authorized
four additional submitted turns beyond the earlier 2/2 ledger. Two were used,
leaving the private ledger at **4/6 total, 2/4 of the extension used**.

Both new turns used the merged split runner, the actual
`openai_chatgpt_plan` provider configuration, and the same pinned `live-107`
skill. In the first turn, the agent checked that `ACCESS_TOKEN` was absent
from its environment and process-1 environment and that its executor had no
Codex `auth.json`. It followed the skill, wrote and read back the skill-only
marker with a shell command, then used `apply_patch` to create a separate
random marker file and read that back. A second Python runner process repeated
the same work with the same nonsecret credential reference, provider subject
hash and credential generation. Both runs completed in distinct native
threads, with completed command and file-change events and matching host-read
files. No access or refresh token was found in either private run directory
or in the persistent controller profile, and no disposable split container
remained. [Sanitized observations](live-route-observation.json) pin the private
trace hashes and the local harness hash; the raw trace and login remain
outside Git. The harness source stays in ignored local scratch, so these
hashes identify the run but do not make it independently replayable without
the private account. The harness directly checked marker files, completed
events, run-file token absence, and the agent's answer; separate host checks
established the credential-check command's exit code, matching credential
reference/subject/generation, distinct processes and threads, controller-profile
token absence, and the final split-container count. The live `apply_patch`
file was in the workspace shared by controller and executor; the corrected
synthetic exact-file probe establishes executor placement for the pinned route.

This establishes the bounded single-user local before/after-process-restart
route with a live shell and `apply_patch` canary. It does not establish actual
refresh rotation, provider revocation, host reboot recovery, event-level
executor attestation, independent network namespaces, legacy routing, or
hosted/multi-user isolation. Docker administrators on the host can still
inspect an active controller token through container metadata. The two
remaining authorized turns were not spent because both required live checks
passed.

The host suite also exercises authorization changes around a turn. A
pre-turn generation change refuses model submission. Synthetic mid-turn
revocation, account switching, generation replacement and refresh uncertainty
end as `unknown` with a distinct sanitized category and outcome; a consumed
turn and partial trace remain recorded. These are fake-server tests, not
claims that a provider-side revocation or refresh was observed live. The
suite passed **227 tests, 4 skipped** at this evidence revision.
