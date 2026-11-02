# Agent controls

Agent tests are grouped by the responsibility they protect. `test_codex` owns
Codex launch/controller policy. Other Agent suites remain at their existing
locations until their concern and shared setup are migrated together; this
package does not claim their organization is complete.

Run `python -m unittest discover -s tests/test_agents -t tests -v`.
CI core discovery is `python -m unittest discover -s "$GITHUB_WORKSPACE/tests" -v`
from `.github/workflows/work-graph.yml`. The move preserves eleven cases
(+11 at the new path, -11 at the retired path); full-suite execution/count
comparison remains pending for the broader refactor. Internal providers are unit
controls, never real Agent acceptance. No test in this package dispatches a model
or changes a remote resource.
