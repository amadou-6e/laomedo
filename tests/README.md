# Tests

Tests follow the concern they protect. `test_shared/` owns architecture, Git, HTTP,
migration, formatting and component-template controls. `test_skills/` owns the registry,
sources, operations, inspection, authoring and workspace delivery. Graph cases
live with their respective Skill concern. `test_host/test_publication/` owns
ingestion, frozen-bundle staging/ownership/worker checks and verified snapshots;
these concerns are not filename families at the test root. Agent/GitHub suites
retain their separately scoped grouping and optional-runtime harness.

Keep `tests/` as the discovery root. Every folder beneath it containing tests,
directly or in nested concerns, starts with `test_`: for example,
`test_skills/test_operations/`. Support-only and data-only folders (`support`,
`fixtures`, `contracts`) keep their descriptive names. `test_skills/test_browser/`
contains the Skill browser controls; `test_browser/` retains the deferred GitHub
controls. `test_langflow/` contains the separately discovered runtime
checks. Folder naming does not change their prerequisites or acceptance status.

## Deferred adjacent suites

The existing root files `test_host_mediated_push.py`, `test_host_services.py` and
`test_host_token_connection.py` cover deferred mediation, service composition
and credentials. Host publication handoff controls live in
`test_host/test_publication/test_handoff`; `test_probe_stage_s7.py` retains an EXP-100 consumer control.
They are explicit exclusions from the Shared/Skills organization pass, even
where they use the same host publication package. Agent/provider, GitHub,
Langflow join, runner and historical campaign families retain their separate
migration scope. Their presence is not permission to add new flat prefix
families: new coverage belongs in its concern package.

## Discovery

Run core discovery against an installed package, including outside this checkout:

```powershell
python -m unittest discover -s C:/path/to/implementation/tests -v
```

`test_shared`, `test_skills`, `test_host` and `support` are packages relative to that discovery
root. Focus an owning package using `-t tests`, for example:

```powershell
python -m unittest discover -s tests/test_skills -t tests -v
python -m unittest discover -s tests/test_shared -t tests -v
python -m unittest discover -s tests/test_host/test_publication -t tests -v
```

The Skill graph modules explicitly skip only when `lfx` is absent. With the
declared Langflow environment installed, the same discovery runs them. An import
failure inside an installed runtime fails normally. Other `tests/test_langflow/`
modules still use the existing separate optional-runtime harness; core discovery
does not include that un-packaged directory. Internal mocks and fixture providers
are regression controls, never evidence of a real graph's acceptance.

## Support ownership and vocabulary

`support.paths.repository_root()` finds this checkout by its package manifest and
source directory, independently of test nesting or the current working directory.
`support.http_server.RunningHTTPServer` owns one supplied loopback server and its
thread. Enter starts it; exit shuts it down, closes its socket, joins its thread
and raises if cleanup remains incomplete. It never touches another server.

`test_skills.test_operations.models.SkillOperationCase` groups the isolated registry,
service, starting revision, raw edit policy and proposal used by service and graph
controls. `prepare()` reserves against that case's exact revision. Its creator
in the concern's `utils.py` makes fresh files/state; it does not reuse a TestCase.
Raw policy/proposal dictionaries deliberately remain raw inputs for rejection
tests; they are not alternative production contracts or derived expectations.

`test_shared.test_migration.utils.load_migration()` loads the actual checkout-owned offline
migration tool and restores the temporary import path. Migration assertions stay
in the test modules. `support.retained` and `support.git` own the existing
hash-pinned historical loader and Git command seams used across these concerns
and deferred Agent/GitHub controls. Their callers import defining helpers
directly; no root forwarding modules remain. Historical dependencies are retained.
No test fetches an experiment branch or requires a second checkout.

`test_skills/test_workspace` retains the exact-byte and Git-isolation assertions from the
archived EXP-08 campaign. It uses the installed registry/materialization boundary
and shared Git command runner; ordinary discovery replaces the old campaign CI
invocation. No archived script or model turn is needed.

Keep helpers small and concern-owned. Consolidate repeated setup, not distinct
error, authorization, wire-format, path, history or cleanup assertions. Compare
test size including support code; moving a file does not reduce it.
