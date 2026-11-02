# Codex ACP controller

`CodexController` owns one admitted controller lifetime and composes
`AcpSession`. `CodexLaunch`, `CodexTurn` and `SplitPolicy` in `models.py` carry
validated launch/turn/policy values. They do not authorize a new effect.

`initialize` and `open` establish the protocol/session; `prompt` submits one turn;
`models` discovers metadata; `preflight`, `check_health` and
`assert_controller_isolated` inspect actual readiness and isolation; `close`
reconciles exact owned resources. `extension` handles only the documented native
evidence/precheck boundary. Private `_close_resources` remains lifecycle plumbing.
Unconfirmed native completion or cleanup cannot produce a successful frozen result.

## Current object interface inventory

This inventory names existing methods; the vocabulary above explains their
roles. Full signatures and detailed parameter contracts remain in source.

| Object | Defining module | Public/framework methods |
| --- | --- | --- |
| `CodexLaunch` | `models.py` | `to_container_spec` |
| `SplitPolicy` | `models.py` | Validated fields / inherited interface |
| `CodexTurn` | `models.py` | Validated fields / inherited interface |
| `CodexController` | `service.py` | `__init__`, `initialize`, `extension`, `open`, `prompt`, `check_health`, `assert_controller_isolated`, `preflight`, `close`, `models` |
| `Settings` | `settings.py` | `settings_customise_sources`, `load` |
