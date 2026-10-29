# Codex ACP runtime

Status: selected by the production runner on draft PR #214; unreleased and not
accepted for merge. Final graph and provider-policy acceptance remain pending.

Build from this directory with `docker build -t laomedo-codex-acp:0.159.2-2.1.1 .`.
Record the resulting immutable image ID before testing or configuring a runner.
The Dockerfile pins the Node base, upstream adapter commit/archive checksum and
Codex package lock. The runtime includes the upstream Apache-2.0 licence and
checksums of the patch, extension and compiled adapter. The Laomedo extension
source is maintained here; `native-events.patch` contains the minimal upstream
hooks needed to activate it.

The optional extension is enabled only by `LAOMEDO_CODEX_NATIVE_EVENTS=1`. It
advertises `_meta.laomedo` version 1 with rawEvents and hostPolicy true during
initialize. The host rejects an absent or incompatible capability before creating
a session, preventing a stock adapter from ignoring the host policy metadata. It
preserves allowlisted native notifications on the same ACP connection and flushes
them before the prompt response. Raw capture failure terminates native execution.
Host-owned session metadata supplies normal or split policy, model, effort and
the one supported output-precheck definition. Normal mode inherits the reviewed
permission profile without per-turn sandbox/approval overrides; split mode uses
only its registered external executor. Typed skill items come from host metadata,
never prompt parsing. ACP slash-command interception is disabled for these runs.
Native session roots remain explicitly untrusted, so model-writable project
configuration cannot become a runner-policy or provider-routing source.

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
establish final graph acceptance. After the cutover, a separate production-runner
check observed Fresh and Resume on one native thread, accepted prechecks, local
OTLP receipt and confirmed cleanup on image
`sha256:d3f53de292540a8e412aa34a43a975b467df2d21aa6bba290cee11956edc03aa`.
The model/effort record is host-requested and adapter-asserted configuration;
it is not an independent native report of effective selection.
Split production, app-owned OAuth, mediation and graph checks remain pending.

Saved runs retain exact image, policy and execution-mode bindings. Pre-ACP runs
with different bindings fail with `resume_binding_mismatch`; they are not silently
migrated or restarted. Historical activity remains readable. Native thread-history
compatibility is a separate observation from saved-run migration.

Named extensions provide model/skill metadata, fixed-enum permission preflight,
one pre-prompt executor registration/status and pure output precheck. They expose
no arbitrary method/command passthrough. Requests outside their scope fail closed.
The host must still enforce skill search-path isolation, safe secret redaction,
native terminal status, auth revocation, executor monitoring and exact-ID cleanup.

Laomedo does not enable upstream payload debug logging (`APP_SERVER_LOGS`), and
private credentials or capabilities must never be written to build inputs.
