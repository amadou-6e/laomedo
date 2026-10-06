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

## Short-lived launcher parentage check (positive but narrow)

After the negative whole-tree result, [amendment](LAUNCHER-AMENDMENT.md)
`bd78351` froze a fresh one-shot Windows diagnostic before the
[probe](launcher_probe.py) `dc29140` ran. Its short-lived launcher started a
marked idle supervisor and exited before an exact `taskkill /T /F` of the
disposable runner. The [machine observation](launcher-observation.json),
SHA-256 `95409d79d7e5becfb4f00a35ff43f0a1415935a42d5dd4621dcd3f7266f1be33`,
records `survived_tree_kill`; the exact surviving supervisor was then stopped.
Zero model turns, no Docker container and no grant were involved.

This **does not overturn** the negative result for the current production
`LeaseProcess`, which still launches its supervisor as a direct child. It only
supports trying the launcher parentage in that path. A separately frozen
production-lease whole-tree/Docker probe is required before #93 can claim the
tested failure boundary, and systemd-cgroup survival and scoped-grant
revocation remain separate gates.
