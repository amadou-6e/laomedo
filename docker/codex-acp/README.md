# Codex ACP runtime candidate

Status: not a released or accepted runner image. The production Codex runner has
not switched to this adapter yet. The current draft must pass normal/split policy,
raw-event, precheck, skill, cancellation and old-thread resume probes first.

Build from this directory with `docker build -t laomedo-codex-acp:0.159.2-2.1.1 .`.
Record the resulting immutable image ID before testing or configuring a runner.
The Dockerfile pins the Node base, upstream adapter commit/archive checksum and
Codex package lock. The runtime includes the upstream Apache-2.0 licence and
checksums of the patch, extension and compiled adapter. The Laomedo extension
source is maintained here; `native-events.patch` contains the minimal upstream
hooks needed to activate it.

The optional extension is enabled only by `LAOMEDO_CODEX_NATIVE_EVENTS=1`. It
preserves allowlisted native notifications on the same ACP connection and flushes
them before the prompt response. Raw capture failure terminates native execution.
Host-owned session metadata supplies normal or split policy, model, effort and
the one supported output-precheck definition. Normal mode inherits the reviewed
permission profile without per-turn sandbox/approval overrides; split mode uses
only its registered external executor. Typed skill items come from host metadata,
never prompt parsing. ACP slash-command interception is disabled for these runs.

`LAOMEDO_CODEX_ARGS` carries host-owned native configuration arguments into the
Codex subprocess. The adapter validates alternating `-c`/`--enable`/`--disable`
flags and bounded string values, passes argv directly without a shell, and fails
closed for malformed data or a missing explicit Linux Codex executable. This
preserves deferred-executor, telemetry and trusted provider routing configuration.
It is not a model- or graph-supplied command interface.

Bounded real probes established normal-mode permission preflight, pinned skill
use, rejected-then-corrected prechecks, native-thread resume across the old Python
wire and ACP, and cancellation with a raw native interrupted completion. The split
prototype established executor registration, command execution in the observed
credential-free executor, no controller listeners, executor-loss detection and
cleanup. The executor required the existing checksum-verified Codex seccomp policy
for Bubblewrap's namespace creation; Docker's default policy refused it. No host
kernel setting or unconfined container was used. These prototype checks do not
establish production-runner or graph acceptance; that cutover is still pending.

Named extensions provide model/skill metadata, fixed-enum permission preflight,
one pre-prompt executor registration/status and pure output precheck. They expose
no arbitrary method/command passthrough. Requests outside their scope fail closed.
The host must still enforce skill search-path isolation, safe secret redaction,
native terminal status, auth revocation, executor monitoring and exact-ID cleanup.

Laomedo does not enable upstream payload debug logging (`APP_SERVER_LOGS`), and
private credentials or capabilities must never be written to build inputs.
