# EXP-100/S3 amendment 04: transfer identity and reused verifier controls

This amendment is committed before changing the S3 candidate or recording an
S3 result. It responds to the independent review of prototype `1f10847`.
It does not change the frozen acceptance cases or permit a live effect.

The transfer identity in `PROTOCOL-03.md` is the tuple `(run_id, attempt_id)`.
The host reserves that identity once; a second call with the same tuple is a
known refusal and must not overwrite the first bytes or result, even if the
second call offers identical bytes. Distinct attempts for one run can carry
different fast-forward commits, but only when the later attempt names a
host-private, previously accepted stage for that exact run and branch. A
second independent first commit without that confirmed stage is refused.

S3 reuses the exact S2 bundle verifier. S3 evidence may cite S2's already
recorded and regression-tested object/header controls for missing objects,
truncation, object-format/filter, hook and hostile-remote isolation, but must
also exercise malformed bytes and a host-Git non-use control through the S3
fixed-file handoff. The S3 result must list reused versus newly exercised
controls separately and pin the verifier source SHA. This is not a relaxation
of any rejection condition.

The first S3 recorded run also needs direct controls for wrong-run bytes,
wrong baseline, concurrent replacement/frozen-byte handling, Windows
link/reparse refusal or an explicit inconclusive result for that platform,
stage placement outside all agent mounts, `git status/add/commit`, and durable
attempt/error recording. It must record Git version and zero provider/model
calls. No unverified run may be described as passing S3.
