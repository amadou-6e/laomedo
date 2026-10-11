# S14: captured systemd boundary, retrospective assessment

Issue #104; governing specs [f6f279f](https://github.com/amadou-6e/specs/tree/f6f279f1785aeba5a9ec9407d716e894fecc8fb1).
Protocol frozen9bcf8be; executed source0be8200bcef6b49c0c99127d2c6024faf5a5379d;
[independent pre-run approval](https://github.com/amadou-6e/laomedo/pull/132#pullrequestreview-5478746913).
Identity exp104-systemd-s14-20261010-a, exactly one run, no replay. Image
sha256:48b88125a5e7e0b03bb166468b3449ad46c263c4c148f9999098f41768dba793.

## Original outcome and disclosed correction

Original [systemd-observation.json](systemd-observation.json) remains unchanged,
`status: incomplete`, `error_class: ValueError`, `cleanup_verified: true`.
SHA-256 of original/committed LF bytes:
`3b064adb74b39255055b61759cfa9925cfbedc2ba8f5bbd3be65d276f3d3db18`.

The fixture completed but the original checker equated full replay responses.
The replay adds `resent: false` without changing its confirmed result or provider
count. [Amendment01](SYSTEMD-AMENDMENT-01.md) at0a44f63 was committed before
checker6232ef1a0430f94a196707851f4162bae8c0e6e3. That checker compares HTTP,
confirmed state/result and unchanged count. A real-metadata positive and a
changed-result negative control pass; all six checker tests pass. Retrospective
assessment of the retained capture passes the synthetic boundary checks. This
does not relabel the original outer run as passed or claim an independent rerun.

## Recorded observations

- PID1 is systemd249.11-0ubuntu3.22. Service and runners A/B have distinct
  systemd unit cgroups; parent/child membership was recorded before the kill.
- Both initial writes confirmed; replay retained the same PR result and provider
  count2. Killing all A-unit processes removed its parent and child.
- A's exact grant was revoked4.914914seconds after kill completion. Its retained
  capability was denied403/grant_unavailable with provider count2 unchanged.
- B's subsequent write confirmed, increasing count to3. B and broker MainPID
  stayed unchanged until the later broker restart.
- Synthetic lost response produced unknown; repeat remained unknown/count4;
  changed content conflicted403 without dispatch. Restart changed broker PID,
  old B was denied/count4, and old-lease renewal was refused. Separately expired
  store grant was denied and could not renew.
- Exact owned outer container cleanup verified. Zero model turns and provider
  credentials. No real GitHub effect or inner stage Docker container exists.

## Limits and protocol deviation

Capture exec allowed200seconds within overall240seconds, rather than the generic
30-second Docker-command statement in the frozen protocol. No time bound was
expanded after dispatch. PID disappearance is not cgroup-emptiness evidence;
PID reuse was not independently excluded. Boot readiness is permissive. Expiry
control is store-level, not a lease-service-tick failure. No B-continuity claim
after broker restart. The synthetic cleanup callback reports no stage container,
not a successful stage cleanup. These are privileged Docker VM cgroup-v1
observations, not host systemd/cgroup-v2/user-linger/logout/double-manager proof.
Full production Linux LocalRunner routing remains refused. Real Linux GitHub
writes, inner-stage teardown, hostile-code isolation and Q11 remain unproven.

Review this capture and analysis before deciding #104 acceptance; #100's native
paired parity matrix is independent and unfinished.
