# EXP-104 amendment 18: S5 result and consumed identity

Date: 2026-10-07. Status: frozen after the one-shot S5 probe and before
post-result code changes. The S5 run at source
`6fc655cc4d96a09163ca544463fc4ea7f58a20bb` returned
`scoped_candidate_pass`. Its machine observation is
[`live-observation-s5-01.json`](live-observation-s5-01.json), copied
byte-for-byte from the private result. S5 made four provider calls across
the allowed control operations; the post-loss A write returned 403 and
caused no additional provider call. No model turn was used. This result
does not establish provider-enforced exclusivity of the user's selected
token, production account connection, real-agent cancellation or Q11.

The next code revision must add `exp104-s5-20261007-01` to the consumed
identity guard. The S5 A effect was confirmed, but one-shot identities are
still never reused. Do not remove the disposable A branch or modify the
token's GitHub settings without separate authorization. Update the result
record with the exact observed timings, read-back, process/container cleanup,
secret-scan outcome and committed-byte hash. Keep the old S3 `unknown`
effect unchanged and never retry it. No fresh live identity is authorized
by this post-result amendment.
