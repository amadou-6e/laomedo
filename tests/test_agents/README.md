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

Historical observation checkers are preserved on `exp` at `8b2f2395` in
`archives/agents-205/test-callers`: `test_native_capture`,
`test_native_localrunner_evidence`, `test_native_managed_checks` and
`test_native_managed_evidence`. They verify campaign-specific JSON hashes,
reconstructed journals and synthetic acceptance oracles, not installed APIs.
Their exact bytes and the underlying campaign artifacts remain historical evidence;
normal test discovery does not claim to reproduce those old campaigns. Current
production receipt retention and uncertainty are checked in `test_activity/`;
provider isolation and cleanup are checked in `test_opencode/`, `test_codex/` and
`test_leases/`. These controls are not substitutes for live campaign acceptance.
