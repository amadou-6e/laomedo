# Prospective native timeout reconciliation, #66

Freeze this protocol and source before execution; obtain the same Claude
reviewer's pre-run verdict. Preserve the earlier Langflow 408/JOB_FAILED
synthetic observations unchanged. These new cases exercise a REAL HOST WAIT
DEADLINE through RunnerTraceBridge and RunnerAdapter, not a new Langflow v2
408 or visible Stop test. #117 supplies the separately observed UI mechanism.
No existing deployment configuration, permissions or authentication changes.

Use the approved private non-split Codex 0.159.2 profile, model gpt-6-luna/low,
a fresh outside-Git state directory per case, one model turn maximum per runner,
and the remaining shared ledger: expected10 for before-effect, expected11 for
during-effect. Reserve immediately before dispatch, refuse repeated/out-of-order
cases and cap at12. Only one run per case; no retry on uncertainty. Preflight
must pass before spending any entry. A failed submission or timeout consumes it.

Reserve/freeze identities in the production store before ONE real HTTP async
POST. The production adapter's five-second host wait expires while execution
may continue. Require the original bound identity, runner_result_pending receipt,
workflow incomplete, evidence false and no redispatch. Do not fabricate a
Langflow server timeout or say its JOB_FAILED confirms native cancellation.

Before-effect task: one blocking shell command sleeps30 then writes FIRST to
native-effect.txt. After the started native command is observed and the host
wait has expired, cancel the exact known native run. The file must be absent.
Absence remains unknown effect-state, not proof of globally no effects.

During-effect task: one blocking shell command writes FIRST, sleeps30 then
appends SECOND to native-effect.txt. Wait until the command started and exact
FIRST bytes are observed AFTER the host wait expired; append a trusted hashed
file observation to the same dispatched invocation. Cancel while the command
is active. A native completion before cancellation makes the case inconclusive.

Both cases require native interrupted, confirmed runner cancellation and exact
owned-container absence. Wait until31 seconds after observing command start;
before remains absent, during contains exactly FIRST (no SECOND). Retain raw
partial events privately, hash them, and reopen the host store in a separate
process. Require same IDs, timeout outcome preserved, native cancellation
receipt, effect-state unknown/before or observed/during, evidence false and one
dispatch. Shutdown the exact runner server; verify exact-container cleanup.

Timing uses host monotonic observations and bracketed wall-clock metadata;
record clock resolution, effective five-second adapter deadline, polling and
31-second effect window. No cross-machine clock inference is made. No GitHub
credentials, grants, writes or agentviz involvement. This establishes only the
bounded local cancellation cases and does not accept outage/revocation under
#93, semantic success, global effect completeness or production login lifecycle.
