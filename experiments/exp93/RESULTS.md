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
