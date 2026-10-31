# Shared test infrastructure

`RunningHTTPServer` is a resource owner, named for its active HTTP server state.
`__enter__` starts one supplied loopback server; `__exit__` shuts it down, closes
it and joins its thread, raising on an incomplete join. Tests keep requests and
assertions outside the helper. It does not manage production services.

`repository_root()` in `paths.py` locates the manifest/source checkout containing
these tests. Helpers are imported from their defining modules; there is no global
TestCase or test-import forwarding layer.
