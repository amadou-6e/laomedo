# Contributing

Use the [architecture index](docs/architecture/README.md) to find the owner of a
behavior. Requirements live in the [canonical specifications](https://github.com/amadou-6e/specs/tree/main/projects/laomedo).

## Branches and experiments

`develop` is the integration branch; `main` contains accepted production work. Use
an existing owning issue, or create one, before starting a task branch named
exactly `<type>/<issue-number>`, using `feat`, `fix`, `docs`, `chore` or
`refactor`. Follow the canonical review rules.

The permanent `exp` branch contains investigations and experiment history. Bring
accepted `develop` changes into it as needed. Never merge `exp` wholesale into
`develop` or `main`. Extract a production-ready change onto its owning issue
branch from `develop`, remove experiment-only scaffolding, and validate that cut.
Use a separate worktree for `exp` so experimental work cannot replace another
agent's active checkout. The same rule is stated in `AGENTS.md` for agents.

Keep disposable probes, campaign harnesses and investigation-only artifacts on
the experiment branch. Keep production regression cases in `tests` and the
smallest useful maintained workflows in `examples`. An experiment branch is not
permission to commit secrets, browser profiles, tokens, private logs, caches or
dependency trees. A campaign's model allowance is not a gate in a normal service.

Preserve actual historical evidence with its original revision and limitations.
Archive approved artifacts before removing them from the production cut. A
production test must not fetch an experiment branch or require its checkout.

EXP-08 is archived on `exp`; its useful assertions live under
`tests/test_skills/test_workspace` and run in normal discovery. Agent/GitHub experiment
sources and their existing test/CI dependencies remain until their separately
selected migration. The retained Shared caller inventory and the
GitHub-owned EXP-100 broker job remain deferred. Activity durability, replay and
projection controls run in the concern-owned production test suite; CI does not
execute the historical EXP-05 or EXP-09 prototypes. Their presence is not permission to
add new experiments to production.

## Test ownership and shared setup

Group tests by concern, such as `tests/test_shared/test_git` and `tests/test_skills/test_operations`.
Every test-bearing folder beneath the `tests/` discovery root starts with
`test_`, including parent concern folders and browser/runtime suites. Folders
containing only support code or data keep their descriptive names.
Use short filenames within those folders instead of repeating the concern in a
flat filename prefix. Keep a distinct failure or security boundary explicit.

Put reused domain setup and helpers beside that concern. Use `tests/support` only
for genuinely shared infrastructure, such as scoped server lifetime or repository
paths. Import the helper itself; do not instantiate another TestCase for setUp,
depend on test order or add forwarding test modules.

Keep policies explicit in factories and give every test fresh state. Consolidate
equivalent cases with a recorded coverage rationale. Do not drop assertions for
authorization, path safety, atomic edits, history, redaction or cleanup uncertainty
to reduce line counts. Expected results must independently check the behavior.

Data that travels together belongs in an owning `models.py` using Pydantic; reuse
the canonical production model when it already expresses the contract. Keep
behavioral classes and standalone functions in separate implementation files,
including test support. Define handlers and other classes at module scope.

Before a move, check discovery, imports, patch bindings, paths, packaged resources
and CI invocations. Verify that core discovery still finds the owned cases and
that optional graph tests run with their declared runtime. A missing optional
dependency gets an explicit skip; an arbitrary import failure is a failure.

Use the [test guide](tests/README.md) for exact commands. Report affected results, skips and
verification gaps. Mocks and fixtures support internal regression checks; working
examples and acceptance require actual agents/integrations and the workspace's
real browser stories. Never label fixtures as a successful real workflow.

## Maintained examples

Lead developers to the smallest set of distinct supported workflows. Each example
states its purpose, prerequisites, run/build command, expected result and current
limits. Reuse setup and pure graph-building utilities where that removes actual
duplication; importing a helper must never start an experiment or provider.

Current templates use production components and user-supplied real references.
They contain no login material or machine-private paths. Keep source/cache hashes,
connections and parameters synchronized when an owning component changes. An
executed historical export is not a current runnable template.

## Formatting and review

Install the pinned formatter with `python -m pip install -e '.[dev]'`. Run
`python -m black .` and `python -m black --check --diff --no-cache .` before pushing.
Follow the declared archived-source exclusions; do not invent exemptions to make
the check pass. CI uses the same configuration.

Commit and push coherent blocks promptly to their issue branches. Keep work in a
draft PR with unfinished checks stated honestly. Use the existing Claude reviewer
session for the full substantive diff and required focused rechecks; do not claim
a review that did not run. Resolve blockers and obtain final configured CI.
Graph/browser work also requires the requesting user's inspection and explicit
validation of the actual final stories before merging. Reviewer approval and
internal tests do not replace that validation.
