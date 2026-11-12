# Suite guard fix (2ed58e5e → bca47f11)

**S-01 is resolved.** The `GraphBuilderTests` skip guard in `test_graph.py:17-19` now checks `find_spec("langflow")`, matching the `import langflow` in `setUpClass` and the guard already used in `test_example.py`. The `lfx` imports that follow are covered too, because the pinned Langflow packages depend on `lfx`. The diff is that one line: the setup, the cleanups and every assertion are unchanged.

**Combined suite-isolation fix (b41d6c4c → bca47f11): code APPROVE, no open findings.**
- The tests no longer depend on the host's private Langflow configuration.
- They still exercise the real settings service and real Graph validation.
- Class cleanups restore the service cache, then the environment, then delete the temporary directory.
- The subprocesses run with the isolated configuration.

**Coverage:**
- I read all of `suite-guard.diff`.
- The earlier `suite-isolation.diff` review still applies.
- I relied on your statements for the test runs and Black.
- The full suite was 37% through with no failures when you sent this, so it is not yet confirmed green.
- CI at the new head is pending.

**Other verdicts:**
- **Visual:** not applicable.
- **Acceptance:** no UI, model or graph-execution acceptance is claimed.
- **Not authorized:** merge or issue closure.