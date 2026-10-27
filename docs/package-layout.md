# Package layout and compatibility

The Python package uses setuptools' `src` layout. Install with
`python -m pip install -e .` for development or install the built wheel.
The minimum Python version stays 3.10; optional provider and observability
requirements retain their existing scope.

```text
src/laomedo/
  agents/                 # Run lifecycle, contracts, artifacts and provider adapters
    providers/
  skills/                 # Registry, sources, operations and materialisation
  github/
    issues/
    pull_requests/
    transport/
  host/                   # Managed startup and independent trusted services
    credentials/
    mediation/
    leases/
    publication/
  activity/               # Capture, projection, telemetry and inspection routes
  integrations/langflow/  # App factory, joins and stage adapters
  work_graph/             # Existing workflow graph domain
  resources/              # Existing byte-identical packaged resources
```

`tools/package-layout.json` maps every retained flat module to its canonical
module. Runtime code has one owner. A legacy import resolves to the identical
module object, preserving exception/class identity, private helper access and
patch targets. These names remain for actual saved Langflow graphs and installed
services; this refactor does not remove their migration window. New component
source imports canonical modules. `output_contract_legacy.py` deliberately keeps
its exact historical import text because the offline migration recognises that
known embedded source. Historical execution exports are not regenerated.

Legacy `python -m laomedo.local_runner`, `laomedo.claude_runner`,
`laomedo.managed_service`, lease supervision and app-factory paths remain valid.
The executable facade branches before importing its implementation and dispatches
the real main via runpy. It cannot silently return success without starting.
The checkout-only root bridge preserves working-directory discovery and existing
editable-install mappings; wheels contain only the package under `src`.
`src/laomedo/__init__.py` intentionally has no executable initialisation; a
regression check requires bridge parity before that changes.

Package-root/import-root helpers replace nesting-sensitive paths. Runner config,
MJS adapters, seccomp policy, script resources and license bytes remain unchanged.
Service bootstrap and Docker stage mounting use the import root; explicit source
roots still must contain the importable package. Explicit source roots accept both the existing checkout root and
`<checkout>/src`; installed import roots continue to work. Credentials remain outside the package and
outside model-callable mounts. The Git credential helper remains a real script
at the stable package-root path. No JSON schema, error code, runner identity,
image pin, request acknowledgement, cancellation or cleanup algorithm changes.

The original `implementation` checkout's unrelated edits remain untouched; this
branch is based on current develop6069ac9. This increment establishes package
ownership and source layout. Further splitting of cohesive runner methods is a
separate behavior-preserving increment, not an unreviewed rewrite in a file move.

Verification distinguishes internal regressions from real integration evidence:
module identity and executable entrypoints, old embedded graph code, package
resources from an installed wheel, core tests and explicit Langflow checks.
Actual managed start, recorded-run Status and an authorised real Fresh run are
required for integration acceptance. Those results are recorded separately;
passing unit tests do not assert the user workflow succeeded.
