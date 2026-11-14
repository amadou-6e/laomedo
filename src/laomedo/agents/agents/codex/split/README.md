# Codex split executor

`Executor` owns an explicitly authorized split execution resource;
`SplitLaunch` in `models.py` binds its admitted launch policy. Construction opens
the admitted resource; `exec_probe` executes its bounded probe, `check_health` and
`assert_controller_isolated` check readiness/isolation, and `close` reconciles
cleanup. The noun identifies an execution resource, not a
second Agent or protocol implementation.

Authority, workspace identity and lease cleanup remain mandatory. Generic Docker
mechanics are delegated to py-docker. A model cannot choose host credential paths
or arbitrarily register another execution backend.

## Current object interface inventory

This inventory names existing methods; the vocabulary above explains their
roles. Full signatures and detailed parameter contracts remain in source.

| Object | Defining module | Public/framework methods |
| --- | --- | --- |
| `Executor` | `executor.py` | `__init__`, `check_health`, `exec_probe`, `assert_controller_isolated`, `close` |
| `SplitLaunch` | `models.py` | `to_container_spec` |
