# Agent regression controls

Concern-owned packages cover protocol/session boundaries, runtime persistence,
Codex, Claude, OpenCode, Activity, workspaces, orchestration and lease cleanup.
Each package contains the existing source branch's assertions with defining
imports and repository-root asset lookup. Internal providers support regression
checks; they are not real Agent or browser acceptance.

Run `python -m unittest discover -s tests/test_agents -t tests -v`.
CI core discovery is `python -m unittest discover -s "$GITHUB_WORKSPACE/tests" -v`
from `.github/workflows/work-graph.yml`. Optional runner coverage needs the pinned
runner extra, including py-docker and the ACP SDK. No default test is intended to
dispatch a paid model. Historical campaign dependencies remain explicit until
archival and replacement; passing discovery alone is not integration acceptance.
