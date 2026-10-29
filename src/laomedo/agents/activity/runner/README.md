# Runner activity transport

`LaunchTelemetry` owns the bounded telemetry listener; `RunnerTraceBridge`
transports correlated trace evidence. `feed.py` exposes paginated retained data.
Construction / `close` own listener lifetime; `arguments` projects native launch
arguments. Trace `dispatch`, `reconcile`, `cancel` and `observe_terminal` retain actual native
identity rather than correlating by timing. The nested handler will be extracted
with an explicit server/owner object, keeping wire and cleanup behavior unchanged.

`Settings` loads configured observation flags at point of use. It must not turn
verification allowances into persistent runtime gates. Missing evidence is not
success, and no credential-bearing native payload may be publicly exposed.

## Current object interface inventory

This inventory names existing methods; the vocabulary above explains their
roles. Full signatures and detailed parameter contracts remain in source.

| Object | Defining module | Public/framework methods |
| --- | --- | --- |
| `Settings` | `settings.py` | `settings_customise_sources` |
| `LaunchTelemetry` | `telemetry.py` | `__init__`, `arguments`, `close` |
| `RunnerTraceBridge` | `trace_bridge.py` | `__init__`, `dispatch`, `reconcile`, `cancel`, `observe_terminal` |
