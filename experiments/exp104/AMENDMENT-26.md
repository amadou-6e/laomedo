# EXP-104 amendment 26: retire pre-write S9 and freeze S10

Date: 2026-10-08. Frozen before S10 implementation and any S10 provider call.
The approved S9 identity `exp104-s9-20261008-01` was invoked exactly once and
stopped at `host_service_identity_mismatch`, before setup grants or any
provider attempt. Its private observation has zero events and no
`provider-attempts.jsonl`. S9 is consumed; it will not be retried.

The cause is the Windows virtual-environment Python launcher used for the
host service: `subprocess.Popen.pid` identified the launcher, while the
service recorded its child Python PID. A local harmless subprocess check
reproduced the mismatch. This affects process ownership as well as the
preflight assertion, so the check must not be relaxed.

The new single-use identity is `exp104-s10-20261008-01`. Its only target is
`ga84jog/laomedo-exp104-disposable-20261007` (ID `1408647759`) at baseline
`1f1a505f2fbd31993a7946924a9bec5a27bb15c1`. Branches are
`exp104-s10-20261008-01-a` and `exp104-s10-20261008-01-b`. Abort if a branch
or PR marker already exists. No S7, S8, S9 or S10 effect may be retried after
an uncertain result.

The fixed sequence, four intended writes, no-model limit and acceptance
criteria in amendments 21–25 apply with S10 substituted for S9. User approval
and the authoritative selected-repository-only token confirmation carry
forward. Before the first provider write, pin the final S10 code and obtain
a fresh independent positive review of that exact head.

The S10 host service and runner processes must be owned directly by their
spawned Python process, not by a transient virtual-environment launcher.
Use the base interpreter executable with an explicit source-root and current
venv site-packages import path, verify parent/child PID equality in a harmless
local control, and retain the strict identity and module-origin checks.
Record the actual host service PID and module root in the observation. Test
the synthetic Docker route with exact A/B grant and cleanup assertions. A
new source pin and review are mandatory after implementation; S9 approval
does not authorize S10.
