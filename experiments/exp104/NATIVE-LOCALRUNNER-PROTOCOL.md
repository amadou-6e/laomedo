# Prospective production LocalRunner capture, S13

Issue #104 / draft #105. Governing specification
`amadou-6e/specs@3f731a5a168cd6bb39da6fa273b53fe4469e94d9`, agent-execution
GitHub write mediation and its bounded S12 evidence. Freeze this protocol
before its executable implementation; freeze exact source and obtain an
independent pre-run approval before the one live attempt.

Fresh single-use identity: `exp104-localrunner-s13-20261010-a`.
Only disposable repository `ga84jog/laomedo-exp104-disposable-20261007`,
ID1408647759, account ga84jog, base main at
`1f1a505f2fbd31993a7946924a9bec5a27bb15c1`. User-confirmed scoped
`GH_LAOMEDO` host-only reference. No ambient gh/GCM fallback, no broadened
grant. Four mutations maximum: A push/create, B push/create; no write retry.
Original S12 captures remain immutable and do not count as this evidence.

Use the existing independently managed Windows per-user host/verifier tasks
with exact action ownership and heartbeat checks. Both production LocalRunner
instances initialize against the same fresh private state BEFORE either
prepares a run, so startup recovery cannot sweep another newly prepared run.
The controller supplies separately approved authority references and local
source clones on the fresh A/B run branches. Real LocalRunner `_prepare` and
`_execute` must bind authority, install a real pinned fixture skill, persist
owned container/lease/grant metadata and launch the actual pinned Git image
through `_open_server`/AppServer.

An explicit test transport subclasses AppServer only to hold after the REAL
initialize response. No Docker command substitution, ownership/record/grant
fabrication or model/turn request. While held, controller executes native
Git fetch/commit/push and supported gh PR create/readback inside that exact
production-owned container. Docker exec adds NO GIT_CONFIG trust override:
safe.directory must come from production launch. Verify exact container IDs,
labels, durable records and unchanged skill exclusion digest. The harness
refuses every other app-server request; runner max_model_turns=0 and exact
local model ledger absent/unchanged reinforce zero turns. Raw initialized
events are retained privately with a hash, not claimed as agent actions.

After A push/create/readback and B push, kill A's verified LocalRunner process
tree. Capture monotonic revocation <=60 seconds, same retained capability
update denied403/grant_unavailable with no new provider journal entry and
unchanged A PR. B must remain active, then create/read back its own PR.
Native commands are controller-driven; no model, agent assessment of PR body,
Q11 timeout/cancellation or completion semantics are inferred.

540-second procedure bound, native commands120s, API15s, denial20s,
readiness25s, task operations35s, state20s, cleanup exact existing bounds.
Timeout is uncertainty, not cancellation; no automatic acceptance rerun.
Record exact source/spec/review hashes, native initialize hash/request list,
run/ownership/grant bindings, provider attempt journal and four mutations,
exact commit/head/base/marker readbacks, service PID/heartbeat continuity,
retained-capability denial, secret-scan limits and each cleanup flag. No
token/capability in public evidence. Native local ledgers must remain absent
or contain zero attempts; shared ledger must remain byte-identical.

Cleanup revokes exact grants before ID/label-verified container removal,
releases B's hold into a deliberate pre-turn fixture failure, waits exact
worker handles, reconciles owned verification containers, removes only
owned task actions, and preserves private roots plus remote PRs/branches.
An incomplete cleanup is a failed cleanup claim, never silently passed.

Credential-free checks must reject wrong source/review/identity, any model
request or turn reservation, missing native initialize, changed ownership,
absent Git trust in production launch, wrong/late revocation, journal growth
on refusal, B failure and incomplete cleanup. Immutable evidence hashes and
independent post-run review precede any promotion assessment.

No Linux/logout/double-manager, full CLI parity, browser login, real-model or
global credential-exfiltration acceptance. This check addresses the real
LocalRunner no-model launch/revocation boundary, not all #100/#93/Q11 scope.
