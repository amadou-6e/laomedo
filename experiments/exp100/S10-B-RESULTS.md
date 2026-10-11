# S10 B: bounded native command integration

Single-use identity `exp100-native-s10-20261010-b`, executed source
`824046dc7fd6870310d4c75db8b6e522d0d4f6d0`, governing specs
`484451161e957f2d7cfafead9a92e27e43493d6e`. Prospective amendments 08-11 and
independent pre-run reviews preceded execution. B ran once; A was not replayed.
No real GitHub token/provider call or model turn. Full #105 remains a draft.

`S10-B-OBSERVATION.json` is byte-identical to the retained probe output;
SHA-256 `99122e350db228ef1e40c0efd42582a73753e809946db2dcacc74e651eddec34`
is also checked against Git-stored LF bytes. It includes command outcomes,
sanitized provider journal, exact source/image, confirmed push effects,
negative controls and cleanup. No bearer, host path or credential is recorded.

## Captured result

- Literal `git fetch origin` acquired a provider-base commit absent from the
  initial agent clone. One listing and one host transport fetch are recorded;
  `fetchedBase` equals the new provider base, not the original run baseline.
- First native push and its exact replay succeeded. A second committed change
  succeeded on the same run branch. Exactly two mediated provider pushes,
  matching the two confirmed effect commits/stage digests and final remote ref.
  Verification-before-push and predecessor CAS follow the reviewed production
  code and its tests; the capture does not independently timestamp each step.
- Supported literal `gh pr create/view/edit/view` created fake PR #7, corrected
  its body and verified body/head/base while the scripted container was still
  owned and alive. REST journal: one POST, one PATCH and five GETs.
- Forced, other-ref and multi-ref pushes exited 1 with no forbidden provider
  target; unsupported `gh auth token` exited 2; unbound PR read exited 3.
  Checkout stayed clean, including the excluded handoff bundle.
- Completed-run direct freeze refused `run_grant_mismatch`; mediated freeze
  remained unknown with no new stage. Completed push, replaced-connection
  read, revoked read and revoked new PR update all refused. Provider counts
  did not change across these host controls.
- Exact agent and both verifier-stage cleanup reports are verified. No B
  container remained in the coordinator's separate post-run Docker query
  (a coordinator observation, not a captured machine field). Synthetic
  renewal was permitted only under exact ownership but was not needed in
  this run (`synthetic_grant_renewals_seconds` is empty).

## Preserved failure and limits

S10 A remains failed, consumed and recorded separately. It showed listing-only
fetch and one confirmed provider push before the second freeze was refused.
B follows a prospectively frozen, separately reviewed production gate fix;
it does not rewrite A's result or reuse its workspace/grant/capture identity.

This is local bare Git and fake REST, a synthetic host credential, scripted
trusted authority and probe-owned service/verifier threads. Two local Git
seed pushes prepare the provider outside the mediated journal; the reported
two pushes and REST counts describe the mediated command sequence only.
Bridge egress was enabled; no network-isolation claim. No production lease,
Windows task lifetime, double failure, real GitHub/model, cancellation or
runner-loss acceptance is established. One small fetch does not bound acquired
disk usage. Supported gh output/commands are partial, not full capability parity.
Only a same-run confirmed predecessor is supported; fresh-run adoption of an
existing remote branch remains unavailable. Unpushed/definitely rejected frozen
stages block later captures; CAS mismatches remain conservatively unknown.

No #100/#104/#93/Q11 acceptance or full #97/#105 merge follows from this result.
[Independent post-run review](https://github.com/amadou-6e/laomedo/pull/105#pullrequestreview-5478075079)
approved the bounded evidence at `f897774`, not full draft promotion. The
reviewer read the prepared diffs and raw observation but did not independently
hash bytes or execute probes. Never execute either S10 identity again.
