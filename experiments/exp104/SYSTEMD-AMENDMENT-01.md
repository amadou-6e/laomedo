# S14 amendment 01: retrospective checker correction, no new execution

The single approved S14 capture ran source0be8200 against governing specs
f6f279f1785aeba5a9ec9407d716e894fecc8fb1. The fixture completed, cleanup was
verified, but the original outer observation remains `incomplete`/ValueError.
It must remain byte-for-byte unchanged, never labelled an original pass.

Cause inspected against original capture: confirmed replay has an additional
`resent: false` member, so whole-response equality fails despite the same HTTP
status, confirmed state/result and unchanged provider count. The mock positive
had identical responses and did not exercise this actual replay metadata.

Freeze this amendment before changing the checker. Compare the replay's HTTP
status, confirmed state and result separately, while keeping exact provider
counts. Add a positive control with real replay metadata and a negative control
whose replay result differs. Assess the retained original capture separately;
save the new checker revision and assessment without overwriting observation.
This is retrospective analysis of captured facts, not a replicated run or a
new acceptance execution. No second privileged run, GitHub write or model turn.

Record disclosures: capture exec200seconds withinoverall240 despite generic
30-second Docker command wording; parent/child PID disappearance rather than
cgroup emptiness; PID reuse not independently excluded; permissive readiness;
store-level expiry; B continuity only before broker restart. Preserve limitations
of privileged Docker VM cgroup-v1 synthetic systemd evidence, not full production
Linux routing, inner stage cleanup, real GitHub/Linux writes or Q11.
