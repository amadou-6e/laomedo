# EXP-93 amendment: short-lived launcher parentage check

Frozen after the negative `GROUP-AMENDMENT.md` result. This is one new,
single-use, zero-model Windows diagnostic with a fresh temporary identity.
It does not rerun the earlier process-tree case or dispatch a production run.

The disposable runner child starts a short-lived launcher. The launcher
starts an idle supervisor child with a unique marker in its command line,
writes the supervisor PID, and exits. Only after the launcher is confirmed
exited and the supervisor is alive does the parent issue `taskkill /T /F` on
the exact disposable runner PID. The parent checks whether that same marked
supervisor remains alive, then terminates only that verified PID. No Docker,
GitHub credential, model, grant or production workspace is involved.

The recorded result is `survived_tree_kill`, `killed_with_runner`, or
`inconclusive`. Survival would support trying the launcher in the production
lease path, not prove systemd-cgroup survival, Docker cleanup, grant revocation
or Q11. Failure leaves #93 draft and points toward an independently managed
service. The probe refuses to overwrite its observation and must not retry a
case after killing the runner.
