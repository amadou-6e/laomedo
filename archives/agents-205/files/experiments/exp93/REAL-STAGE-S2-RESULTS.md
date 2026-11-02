# S2 real-stage attempt: incomplete, 2026-10-11

Fresh protocolcd1033c preceded executed source
5c5d28efba7fd83a22fcb81d32712f7931d859b7 and independent pre-run approval.
Identityexp93-real-stage-s2-20261011-a is consumed and must never be reexecuted.
The original [machine observation](real-stage-s2-observation.json) reports
one native turn, shared14/16, zero provider writes and all six final cleanup
flags true. The active commandExecution boundary was observed with exact live
container ownership before the verified runner-tree kill.

The capture is **incomplete**, failure_code
service_cleanup_unverified_or_late. It does not show a successful service cleanup,
timed absence, post-revocation refusal, B continuity, delayed sentinel or restart
accounting pass: the probe stopped before those checks.

Read-only post-run diagnostics of the exact lease results found A's reason
heartbeat_lost, revocation at host-monotonic1816.562, cleanup-finish1821.671,
cleanup_verified=false and state=never_observed. B's grant-expired cleanup
occurred during final harness cleanup, not a demonstrated continuity pass.
These figures are retrospective selected fields, not the original observation.
Private result files are retained; secrets/capabilities/raw transcripts stay
private. A separate sanitized diagnostic projection may be committed for review.

The production cleanup watcher begins observing after the loss; it cannot
distinguish an already launched/removed container from one not yet created when
it sees no container during the watch. The hypothesis is that Docker's attached
client exited on the runner-tree kill and removed A before service inspection.
That cause is not established by this capture. No passing cleanup is inferred
from final absence or harness cleanup. Two additional authorized turns remain.

Next work is a credential-free investigation of durable, service-owned prior
exact-container observation and watcher behavior before any new real-agent case.
Keep original negative/incomplete evidence and freeze any revised protocol and
source independently; do not silently weaken the acceptance criterion or rerun S2.
