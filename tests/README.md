# Tests

Tests follow the concern they protect. `shared/` owns Git, HTTP, migration,
formatting and component-template controls. `skills/` owns the registry, sources,
operations, inspection, authoring and workspace delivery. Graph cases live with
their respective Skill concern. Other domains retain their existing layout;
this is not a completed repository-wide test reorganization.

Run core discovery against an installed package, including outside this checkout:

```powershell
python -m unittest discover -s C:/path/to/implementation/tests -v
```

`shared`, `skills` and `support` are test packages relative to that discovery
root. Focus an owning package using `-t tests`, for example:

```powershell
python -m unittest discover -s tests/skills -t tests -v
python -m unittest discover -s tests/shared -t tests -v
```

The Skill graph modules explicitly skip only when `lfx` is absent. With the
declared Langflow environment installed, the same discovery runs them. An import
failure inside an installed runtime fails normally. Other `tests/langflow/`
modules still use the existing separate optional-runtime harness; core discovery
does not include that un-packaged directory. Internal mocks and fixture providers
are regression controls, never evidence of a real graph's acceptance.

## Support ownership and vocabulary

`support.paths.repository_root()` finds this checkout by its package manifest and
source directory, independently of test nesting or the current working directory.
`support.http_server.RunningHTTPServer` owns one supplied loopback server and its
thread. Enter starts it; exit shuts it down, closes its socket, joins its thread
and raises if cleanup remains incomplete. It never touches another server.

`skills.operations.models.SkillOperationCase` groups the isolated registry,
service, starting revision, raw edit policy and proposal used by service and graph
controls. `prepare()` reserves against that case's exact revision. Its creator
in the concern's `utils.py` makes fresh files/state; it does not reuse a TestCase.
Raw policy/proposal dictionaries deliberately remain raw inputs for rejection
tests; they are not alternative production contracts or derived expectations.

`shared.migration.utils.load_migration()` loads the actual checkout-owned offline
migration tool and restores the temporary import path. Migration assertions stay
in the test modules. Existing root `retained_shared.py` and `git_runner_controls.py`
remain shared by deferred Agent/GitHub controls; their historical dependencies
are retained. No test fetches an experiment branch or requires a second checkout.

`skills/workspace` retains the exact-byte and Git-isolation assertions from the
archived EXP-08 campaign. It uses the installed registry/materialization boundary
and shared Git command runner; ordinary discovery replaces the old campaign CI
invocation. No archived script or model turn is needed.

Keep helpers small and concern-owned. Consolidate repeated setup, not distinct
error, authorization, wire-format, path, history or cleanup assertions. Compare
test size including support code; moving a file does not reduce it.
