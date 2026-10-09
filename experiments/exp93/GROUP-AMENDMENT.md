# EXP-93 amendment: whole-tree termination boundary

Frozen after the first EXP-93 result and after review. This is a new,
single-use, zero-model diagnostic, not a repeat of the original Docker case.
It tests whether the updated Windows supervisor survives termination of the
disposable runner's **whole process tree**. It does not claim to test systemd.

The probe creates a fresh temporary run record and a disposable child Python
runner. The child starts the production `LeaseProcess`, records the exact child
and supervisor PIDs, then waits. The parent verifies both PIDs belong to that
fresh probe, invokes `taskkill /T /F` on the exact child PID once, and checks
whether the supervisor lives long enough to write its lease result. No Docker
container, GitHub token, model, or workspace outside the temporary fixture is
created. The expected result is recorded even if negative; never retry the
same identity. On exit, the probe may stop only its exact remaining supervisor
PID after verifying its command line and fixture token.

The result must distinguish `survived_tree_kill`, `killed_with_runner`, and
`inconclusive`. Surviving this tree test does not prove survival of systemd
cgroup stop, Windows job-object termination, power loss, or credential
revocation. A negative result keeps #93 draft and requires a supervisor owned
outside the runner's fate boundary.
