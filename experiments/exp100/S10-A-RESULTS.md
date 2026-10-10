# S10 A: failed native integration capture, preserved

Identity `exp100-native-s10-20261010-a`, exact reviewed executable `6db1dff`.
Frozen amendments 08/09 preceded execution; pre-run review approved the corrected
executable. The probe-produced observation is committed byte-for-byte unchanged;
SHA-256 `a37d176dc91b216e904d597ead1434002468cb5cc19b52a824a3b2698b90af99`
matches the retained private original and Git-stored LF bytes.
Zero model turns and zero real provider calls. This is not successful acceptance.

Literal configured-base fetch and the first push succeeded. An exact repeated
push succeeded without a second provider push. The second committed change's
push failed. One local provider push, zero REST calls, no PR. The helper journal
for the first commit is confirmed; the second is freeze_requested. Exact agent
and stage cleanup verified. The identity is consumed and will never run again.

Post-run review clarified the fetch limit: the agent clone already contained
the base object, so only provider ref listing occurred. There is no host
transport fetch in the observation. A does not prove object acquisition,
bundle import or the fetch delivery recheck; B must explicitly exercise them.

Read-only diagnosis: `bundle_ingest._require_reconciled_prior_attempts` permits
only refused/no-input predecessors. It rejects a frozen predecessor even after
verification and a confirmed push; the native helper's second freeze therefore
never creates another stage. This is a production integration gap missed by
isolated transport tests. It does not show a failure of provider CAS itself.

Next bounded change must authorize progression only from a still-run/grant-bound,
fully verified, cleaned stage whose exact stage digest has a confirmed mediator
Git-push journal entry. Unknown, unverified, failed, changed, differently bound
or non-confirmed predecessors must remain blocked. Preserve this result and
freeze a fresh follow-up identity/protocol before any later capture.
