# Original Agent PR feedback verification

Frozen before model execution, 2026-10-15. User selected completing the original
PR → existing LaomedoCodexAgent → same PR Operation workflow and authorized any
needed PR in ga84jog/laomedo-exp104-disposable-20261007.

Use the existing Docker LocalRunner and pinned Codex 0.159.2, real pinned skill,
dedicated local credential volume and real GitHub transport. Host provider tokens,
grant references and feedback tickets never enter graph fields or Agent tasks.
Only required Codex login material is authorized in that dedicated local volume;
do not copy a full profile or permit simultaneous refresh by host/container.

The zero-turn Docker preflight must pass positive workspace-write and negative
canonical/store/auth-read controls. Record actual immutable image identity and
source revision, including the Docker recovery dependency. No privileged mode,
new Agent component or fake-provider substitute is allowed.

Maximum three model turns across this verification campaign, at most 210 seconds
per attempt. One initial happy-path model turn should produce a content-only
proposal and one real description update. A second may check native cancellation;
reserve the third only for a clearly diagnosed failure before an uncertain effect,
never as an automatic retry. Count attempted starts durably before dispatch.
Stop on uncertain model-start or GitHub-write outcomes and reconcile existing
identities before considering another attempt. Do not reset the turn ledger.

Use a newly created disposable real PR with a same-repository head. Verify the
selected reference, initial/final description, exactly one graph Agent invocation,
one confirmed host-mediated effect, native session/turn identity, skill revision
and container cleanup. Read GitHub independently after execution. Test missing
host scope and stale digest before a model turn; replay the same host ticket
without another model call to check one GitHub effect. Internal negative controls
for identity injection, expiry/revocation/rotation and unknown effects remain
internal tests, not real-provider acceptance.

Publish only sanitized evidence, source/graph hashes, public PR URL, native IDs,
outcome counters and limitations. Keep auth, API tokens, capabilities, tickets and
raw provider/model receipts in private local runtime state outside Git. Do not
publish raw account/tool data. Leave the real PR available for user inspection.
