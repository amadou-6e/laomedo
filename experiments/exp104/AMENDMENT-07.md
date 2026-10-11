# EXP-104 amendment 07: revocation control for an exact-branch grant

Date: 2026-10-07. Status: frozen before any Git push. This amendment applies
only to separately labelled `EXP-104-D2`; it does not silently change the
original live protocol or turn a diagnostic into acceptance evidence.

The original post-loss case asks A's *same capability* to push a different
new branch, but the implemented grant authorizes one exact branch. Such a
request would fail `push_branch_denied` even if the grant had **not** been
revoked. It therefore cannot establish grant revocation. Do not use that
false-positive control.

For D2, after A's initial confirmed push and exact runner loss, send one
fresh effect ID using the **same approved branch** and exact commit. Require
the mediator's `grant_unavailable` refusal at grant lookup, before diff
classification, credential resolution or any provider call. Independently
read back the branch and confirm its SHA has not changed. B's separate grant
must still complete its approved read. Record effect and provider-call counts.
Do not retry an unknown outcome.

This proves only the narrow revocation boundary if observed. The original
protocol needs a reviewed correction that either uses an authorized
same-branch control or explicitly grants a second branch; D2 cannot satisfy
the uncorrected wording.
