# Opencode Agent

## Go subscription allowances

`OpenCodeSubscriptionQuota` in `quota.py` reads the fixed HTTPS Go usage endpoint
with the same admitted private profile key used for execution. `read()` validates
key custody before and after one bounded GET. A standard-library HTTP subprocess
receives the key only on stdin; a hard 15-second timeout kills and joins that
process even during DNS or a slowly streaming body. Its environment excludes
provider credentials and its stderr is discarded. Redirects, retries, native sessions
and model prompts are forbidden. `project()` returns the reported rolling,
weekly and calendar-month meters as primary, secondary and monthly windows.
Monthly resets come from the provider, never an assumed 30-day duration.
Missing scalar evidence remains unknown. HTTP 401, 403 and 429 become safe
authentication, subscription-access and retry categories; raw bodies and keys
never enter quota observations or diagnostics. A failed read does not change
the connection's authentication state or infer a zero allowance.

Model discovery is scoped to `opencode-go`, the provider admitted by the dedicated
Go credential profile. The native CLI's global catalogue also includes free
models that the authenticated ACP session does not advertise; they must not be
offered as runnable selections for this connection.

## Assistant native commands

`OpenCodeCommands` in `commands.py` validates no-argument built-ins, projects
the observed catalog, admits its exact image-bound revision, and verifies
native root/child terminal history. `result()` returns `OpenCodeCommandResult`
with session/message identities and the actual target. It does not invent
an answer, usage, repository review or a file write.
Terminal admitted tool/assistant errors produce `opencode_native_command_failed`,
not an uncertain-running outcome. Incomplete or unadmitted native work still
produces `opencode_response_not_terminal`; neither gets a success receipt.

Native `init` and `review` target the isolated controller view containing
agent configuration, not the worker workspace or a user repository. The
approval discloses that distinction; only worker-tool writes reach retained
scratch files. OpenCode 1.18.33 namespaces MCP prompts with `server:prompt`,
so they cannot replace bare built-in names. Custom config/skills are refused
for this admission path. Real execution acceptance remains separately required.

`OpenCodeAgent` is the provider-qualified concrete Agent. It inherits the [abstract lifecycle](../base/README.md).
The implementation is in `agent.py`; folder and object renaming do not
remove its whole-pipeline overrides.

`OpenCodeAgentRuntime` in `runtime.py` owns the configured attempt environment and
exact native session. `OpenCodeCommandExecutor` in `executor.py` owns workers;
`http/broker.py` only adapts MCP. `OpenCodeCredentialProvider` in `credentials.py`
validates the borrowed native profile. `OpenCodeModelCatalog` in `catalog.py` owns
zero-turn discovery; `read_activity` with internal `activity/projection.py` helpers owns
native interpretation and pricing. See the [role methods](../README.md#provider-role-contracts-275).

Credential-free command workers trust only their fixed `/draft` mount as a Git
safe directory through a three-key process environment. This supports host-owned
bind mounts without global wildcard trust, profile mounts or inherited credentials.

The controller and broker span an attempt. Native history export follows confirmed closure and precedes the final freeze. Output requirements are currently unsupported.

| Method vocabulary | Provider contract |
| --- | --- |
| `runtime_binding()` | Public provider/runtime identity metadata; never credentials. |
| `model_catalog()` | Native model/effort discovery without a model turn. |
| `preflight()` | Check configured readiness/isolation; do not dispatch work. |
| `resume(...)` | Continue only an admitted existing provider/session binding. |
| `recover_interrupted(record)` | Reconcile exact recorded resources, without replaying execution. |
| `_execute(...)` | Protected provider hook implementing execution and finalization. |

Native `activity/` and authentication under `auth/` (where implemented) belong
to this provider. `settings.py` owns protocol pins/configuration; `models.py`
owns structured values where present. No empty auth/model modules are required
for symmetry. Provider-independent secure storage, grants and Docker mechanics
retain their shared owners. Sibling provider imports are forbidden.

`OpenCodeConfig` in `models.py` groups permission rules, broker port and the
private capability. `to_config()` projects the native controller configuration;
normal dumps/reprs exclude that capability. Trusted host routing and startup
extensions retain their existing validation and run after this base projection.
The `http/` package owns `BrokerHttpServer` and `BrokerRequestHandler` with an
explicit broker reference; `do_POST` is the framework callback, not a new Agent API.

Start/resume/status/cancel use the base contract. The interface must explicitly
report unsupported capabilities and preserve unknown usage or partial evidence.
Successful execution, capture completeness and cleanup confirmation remain
separate facts. Existing stable error codes and persisted records do not change
with the Python object name.

## Runtime identity value

`OpenCodeRuntimeIdentity` groups the controller/worker images, profile identity,
CLI version and existing keyed credential fingerprint. `OpenCodeAgentRuntime` keeps
that object internally; its `runtime_identity` property calls `to_payload()` only
for the existing provider fingerprint boundary. Profile identity read from legacy
JSON retains its admitted shape. The fingerprint is metadata, never a login token.

## Exact resource closure

The backend and broker register exact allocated receipt paths before dispatch.
`close()` stops admission, closes the controller, drains the broker, reconciles
those paths through the SDK, then closes the Docker client. Partial construction
has optional handles and no invented resources. An unresolved drain/receipt/cleanup
keeps termination unverified; no job or model retry occurs. Existing startup
receipt scans remain unchanged, including their shared-directory lock limitation.

`models()` maps SDK cleanup uncertainty to `opencode_container_cleanup_unverified`
before its generic startup mapping, preserving safe SDK metadata. In-run failures
use the shared private attempt snapshot after normal writes; metadata discovery
has no attempt or new store and retains its existing HTTP code boundary. A true
`opencode_owned_resources` cleanup fact requires all allocated catalog/controller/
worker resources, not controller absence alone. It never accepts a failed run.

Host composition may pass `profile` to `OpenCodeAgent` to select its existing
isolated `OpenCodeAgentRuntime`. The profile stays host-owned; combining it with
an independently supplied transport factory is refused. Construction without
either retains the explicit isolated-transport-required readiness result.

Model discovery runs the pinned native `models --refresh --verbose` command so
the bundled registry cannot offer a retired model that ACP no longer advertises.
Before configuring a model, `_run_acp()` checks the session's current flat or
grouped selector options. Missing choices fail as `opencode_model_not_connected`
before configuration or prompt dispatch; saved selections are never substituted.
# Saved profile construction

`OpenCodeAgent(..., profile=...)` binds an explicitly admitted private profile to
its native runtime factory. Supplying both a profile and a transport factory is
refused. Application callers construct the Agent through `AgentProviderRegistry`;
they never import or construct the provider's private runtime.

## Saved account connections

On Windows, disposable controller configuration and its read-only skill view
are staged in a unique child of the admitted private profile, alongside the
already readable native session store. No credentials are copied. Evidence and
Docker receipts remain in the run/catalogue root. Confirmed runtime closure
removes its staging child; uncertain cleanup retains it for diagnosis.
Disconnect also removes exact `controller-<32 hex digits>` children after the
existing native-stop confirmation, including leftovers from a crashed process.
It does not sweep live profiles at runtime construction or touch other folders.
`utils.remove_controller_directory(root, profile)` checks the exact owned name
and parent, refuses links/reparse points, and retries only read-only copies
within that checked directory. Source skill attributes are never changed.

`connection.py` is the provider boundary. GoConnection owns save/profile/summary/erase for explicit Go subscription keys. It reports custody rather than verified identity and has no asynchronous browser login workers. Exact repeated keys reuse the existing connection. The shared Agent connection service owns admission/index fencing; host storage and profile authorization remain separate.
