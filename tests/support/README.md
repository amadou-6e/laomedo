# Shared test infrastructure

`RunningHTTPServer` is a resource owner, named for its active HTTP server state.
`__enter__` starts one supplied loopback server; `__exit__` shuts it down, closes
it and joins its thread, raising on an incomplete join. Tests keep requests and
assertions outside the helper. It does not manage production services.

`repository_root()` in `paths.py` locates the manifest/source checkout containing
these tests. Helpers are imported from their defining modules; there is no global
TestCase or test-import forwarding layer.

| Owner | Object or function vocabulary | Responsibility |
| --- | --- | --- |
| `git.py` | `CallbackGitRunner._execute`, `InspectingGitRunner.run` | Reuse production command/environment projection while intercepting or observing explicitly scoped test effects |
| `retained.py` | `load_retained_shared`, `refuse_private_git_api` | Load only hash-pinned historical callers with declared import adaptation; refuse removed private Git execution paths |

Git runner objects are class-only support; the retained loader is function-only
support. Their consumers span Shared, host publication and deferred Agent/GitHub
controls. The loader is not a production compatibility facade. Historical code,
the declared dependency inventory and its refusal behavior are not reorganized.

`assert_secrets_excluded(testcase, model, secrets)` in `model_assertions.py` checks ordinary repr, string, dump and JSON forms. Callers supply only test secrets; expected domain payloads remain independent in their owning tests.

`agent_access_violations(source, roots, members)` in `interface_contracts.py` checks declared Agent receivers and their direct assignment aliases for private or undeclared member access, including literal `getattr`. This bounded AST guard does not infer arbitrary runtime types or dynamic calls. Provider-composition imports are separately checked outside provider owners.
