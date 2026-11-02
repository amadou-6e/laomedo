# Agent controls

Agent tests are grouped by the responsibility they protect. `test_codex` owns
Codex launch/controller policy. Other Agent suites remain at their existing
locations until their concern and shared setup are migrated together; this
package does not claim their organization is complete.

Run `python -m unittest discover -s tests/test_agents -t tests -v`.
Core discovery uses the same initialized packages. Internal providers are unit
controls, never real Agent acceptance. No test in this package dispatches a model
or changes a remote resource.
