# EXP-93 result: independent exact-container cleanup

The one-shot case ran on 2026-10-06 after protocol commit `47c09ed` and
implementation/probe commit `fd090ac`. The machine-written
[`observation.json`](observation.json) is the primary evidence. Its committed
LF-byte SHA-256 is `042ce591787d527a80ac5f334696e1e9a071cc45a512ceef8aa7ac9e24f55f64`.

| Check | Observation |
| --- | --- |
| Exact ownership before kill | Saved run reservation matched the running container's name, ID and two ownership labels. |
| Runner hard kill | One child process killed once; no run redispatched. |
| Independent cleanup | Owned container absent within a measured upper bound of 0.39 seconds, below the selected 60-second bound. |
| Negative control | An unrelated same-prefix container remained running. |
| Startup sweep | The saved run became `interrupted`/`runner_restarted` with `cleanup_verified=true`; the exact container was already absent. |
| Model turns | Zero; no turn ledger was created. |

This validates the crash/Docker ownership boundary under one synthetic launch.
The worker was a labelled `python:3.9-slim` sleeper, not a Codex agent. No
scoped external-write grant or real push credential was issued, so this result
does **not** establish grant revocation or first-slice Q11 acceptance. The
current local runner has a shared Codex auth volume, not a per-run GitHub push
grant; no claim is made that killing the container revokes a credential that
could have been copied elsewhere. A separately reviewed grant path and bounded
real-stage check are required before a push-capable first slice.

Unit tests additionally refuse a lookalike with conflicting labels and remove
the inspected container by ID rather than by name. The full host suite passed
171 tests with two skipped before the probe. No real model turn was spent.

## Whole-process-tree follow-up (negative)

The later [frozen amendment](GROUP-AMENDMENT.md) `d16238d` and [committed
probe](group_probe.py) `c832ac8` tested the review's stronger Windows process
boundary once, after the separate-process-group code at `cdf2599`. The exact
disposable runner child was killed with `taskkill /T /F`. Its supervisor wrote
no lease result within 8.609 seconds and was no longer running. The
[machine observation](group-observation.json) has SHA-256
`f9a9b1d5eabb669c1658320e6f1cb6c228dfe461f376062a720d8e50e83b529c`.
The classification is `killed_with_runner`.

This is **negative evidence**: Windows process-group/job-breakaway flags do
not protect the current child supervisor against this whole-tree kill. No
Docker container or grant was used in this case, so it does not independently
test post-kill Docker cleanup. It does show the present lease process is not
an adequate standalone owner for the required whole-tree failure boundary.
The original single-process-kill result remains valid only for its narrower
case. #93 and Q11 remain open; a supervisor outside the runner's process tree
and a scoped-grant revocation test are still needed. No model turn was used.

## Independent lease service under whole-tree kill (amendment 2, pass)

After the negative whole-tree result, supervision moved out of the runner into
an independently started lease service (`laomedo.lease_service`, implementation
`4fef6f7`). The [frozen amendment](SERVICE-AMENDMENT.md) `b9e6a56` preceded the
[committed probe](service_probe.py) `d0cf8a8`; the case ran once. The
[machine observation](service-observation.json) has LF-byte SHA-256
`479c8ac735298190f61c267dcce2353c06e2671d359081701e155cf52e05ae1c`.

| Check | Observation |
| --- | --- |
| Kill scope | `taskkill /T /F` of the exact disposable runner tree, once |
| Service survival | Service process still running with a fresh heartbeat after the kill |
| Grant revocation | Lease result `heartbeat_lost`; the run's grant revoked **4.921 s** after the kill |
| Exact container | Owned writer container absent **5.568 s** after the kill; `cleanup_verified=true` |
| Write denial | No accepted write logged after revocation; a post-revocation write returned **403** |
| Negative control | The same-prefix lookalike with other labels kept running |
| Model turns / GitHub tokens | Zero / zero |

The owned container ran the pinned `laomedo-codex-boundary:0.159.2` image as a
synthetic writer that POSTed through `host.docker.internal` with its grant until
removed. Writes it made between the kill and revocation were still accepted;
that ~5-second exposure is the configured heartbeat-loss threshold, inside the
selected 60-second bound.

This establishes, for this Windows process-tree kill, that the lease service sits
outside the runner's fate boundary and enforces revocation of the run-scoped
synthetic write grant it issues. It does **not** establish: a systemd-cgroup or
Windows job-object stop that also contains the service; power loss; revocation
of a real push credential or of any credential copied outside the grant broker;
a Codex agent run; or the double failure in which the service dies too (the
synthetic grant endpoint disappears with it, but container cleanup then waits
for the runner's startup sweep). #93 and Q11 remain open for those and for a
separately authorized bounded real-stage check.
