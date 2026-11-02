# Prospective real-stage crash/revocation test, #93 / #22

Owner authorization on 2026-10-11 adds four attempted model turns to the exhausted
shared cap12: new total cap16. The old twelve entries and consumed experiments
remain unchanged. Reserve before dispatch, including failed starts. This first
case uses at most one turn, gpt-6-luna / low, and leaves the other three unused.
No automatic retry or replacement identity. Freeze executable source and obtain
independent pre-run review before any model invocation.

Governing specs: amadou-6e/specs at
56642addc7b634b41ea4cc9808124438f239e24b, agent-execution readiness, authentication,
mediated transport and validation. Accepted #100/#104 scope is not reopened.

Fresh consumed-once identity: exp93-real-stage-s1-20261011-a. Windows per-user
managed host/verifier tasks, exact action/configuration/PID ownership checks,
real production LocalRunner launch, pinned Git-enabled native image and existing
private native login volume. Token source GH_LAOMEDO remains host-only, only
ga84jog/laomedo-exp104-disposable-20261007, baseline main
1f1a505f2fbd31993a7946924a9bec5a27bb15c1. No ambient login fallback, workflow edit,
new remote branch, push, PR or issue creation, credential export, model resume or
graph recovery. External acceptance calls are read-only except an intentionally
denied post-revocation PR-create request, which must never reach GitHub.

Construct two real runners before dispatch so startup sweeps cannot interrupt
the other run. Both use fresh independent checkouts/states bound to the same
managed service. B remains held after native initialize and consumes zero model
turns. A executes one fresh native turn with this verbatim task:

Run exactly one shell command: sh -c 'sleep 60; printf TOO-LATE > crash-marker.txt'. Do not run any other commands, use GitHub, inspect credentials, or modify any other files. This is a disposable crash-cleanup test.

Before dispatch reserve the new shared ledger entry, persist run/invocation,
grant, exact container ownership and configuration, and capture preflight pins.
After the matching native item/started commandExecution event containing sleep60
is durably observable, verify exact Docker ownership and active runner identity.
Kill only A's verified Windows process tree once. No blanket container deletion.
If the command is missing/terminal within45seconds, cancel/revoke exact owned
resources, preserve invalid/inconclusive evidence, and do not repeat.

Within60seconds after verified kill completion require the independent service
to revoke the exact A grant and remove its exact owned container. Independently
query Docker by ID/labels; a second B container must still be owned and running.
Capture retained A capability PR-create denial403/grant_unavailable and unchanged
provider journal count. B then performs one read-only repository-scoped REST
request with its distinct live grant, and that provider read must succeed.
This tests real-agent lifetime plus the real mediated grant, not an agent-authored
push or automatic rollback. Earlier S13 live write-denial evidence stays separate.

After61seconds from the observed command start, check the disposable named file:
absence is only a delayed sentinel observation, exact container absence carries
the stop claim. Reopen runner state to capture interrupted/restart accounting,
retaining partial native events and original IDs without redispatch. The raw
model stream stays private; public evidence includes whitelisted selected native
events, hashes, ledger counts, provider attempt metadata, timings, independent
Docker/service/control queries and separate cleanup flags. No fabricated native
interrupted event is required after hard kill; native terminal may be unknown.

Cleanup revokes both grants first, removes only verified exact containers/stages,
releases B into a deliberate pre-turn fixture failure, waits exact worker handles,
and removes only owned scheduled-task actions. No remote audit refs or user files
are deleted. Always attempt cleanup even if evidence/ledger finalization fails.
Overall procedure bound600seconds; start/kill/read/cleanup deadlines must be
recorded in code. Failed cleanup or unknown revocation is not a passing result.

Pre-run local controls must reject wrong identity/source/review, an exhausted or
out-of-order budget, duplicate invocation, missing command boundary, wrong or late
grant revocation, a refusal that grows the provider journal, a failed B control,
ownership mismatch or incomplete cleanup. Post-run independent review plus pinned
spec evidence precedes merge/closure. This does not accept power loss, service
double failure, Linux real-agent execution, arbitrary effect completeness,
production browser login, hostile-code isolation, or all Q11 gates.
