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

Named extensions provide model/skill metadata, fixed-enum permission preflight,
one pre-prompt executor registration/status and pure output precheck. They expose
no arbitrary method/command passthrough. Requests outside their scope fail closed.
The host must still enforce skill search-path isolation, safe secret redaction,
native terminal status, auth revocation, executor monitoring and exact-ID cleanup.

Laomedo does not enable upstream payload debug logging (`APP_SERVER_LOGS`), and
private credentials or capabilities must never be written to build inputs.
