# Contributor instructions

## Experiments and production work

- Use the permanent `exp` branch for new experiments, disposable probes, campaign
  harnesses and experiment evidence. Follow `CONTRIBUTING.md`; do not add these
  artifacts to `develop`, `main` or production PRs.
- Use a separate worktree for `exp` and preserve other agents' checkouts. Bring
  accepted `develop` changes into `exp` as needed; extract production-ready work
  onto its own issue branch from `develop`. Never merge `exp` wholesale back.
- Preserve historical files on `exp` before production removal. Move useful
  assertions into concern-owned tests rather than importing campaign scripts.
  Production tests must not fetch or require `exp`. No secrets or private runtime
  state belong in either branch.
- Remove retained campaigns only in their owning feature's selected migration,
  after exact-source archival and useful regression ports. Remaining dependencies
  are explicit scope constraints, not examples to follow for new production work.
  The GitHub-owned EXP-100 broker dependency remains separately scoped.

## Python formatting

- Install the pinned formatter with `python -m pip install -e '.[dev]'`.
- Run `python -m black .` after editing Python and
  `python -m black --check --diff --no-cache .` before pushing. CI enforces the
  same project-wide configuration in `pyproject.toml`.
- Preserve the exact archived sources listed in
  `docs/architecture/python-formatting.md`; do not broaden exclusions or add
  `fmt: skip/off` merely to avoid formatting maintained code.
- Update the Black development dependency, required version and `uv.lock`
  together when upgrading the formatter.

- Before merging any PR, use the Claude reviewer workflow at
  `specs/shared/skills/claude-reviewer/SKILL.md` in the workspace's canonical specs
  checkout (normally the sibling of this implementation checkout).
  Review the full substantive diff against its intended base, including earlier
  commits. Prepare exact base/head revisions, applicable specifications and checks.
- Reuse the workflow's reviewer session for the current Codex conversation.
  The reviewer is read-only; it cannot publish, mutate issues, or run model probes.
- Address confirmed findings and run affected checks. Obtain the prescribed
  focused recheck for blocking findings. Record reviewed revisions and the verdict.
  Merge only with resolved review blockers and passing required checks.
- In every PR handoff or status report, explicitly state the reviewer status,
  including after the user says "continue". Use "fully unreviewed — reviewer
  pending" when no review covers the substantive change; use "recheck pending"
  only when an initial review covered that change and its corrections await
  review. For reviewed work, identify the reviewed base/head and verdict, and
  disclose any later changes outside that review. Passing checks, earlier reviews
  of other changes, publication and user instructions to continue do not establish
  review coverage. Never describe unreviewed work as approved or ready to merge.
- If a review recommendation conflicts with the user's instructions, pause that
  decision and ask the user; a reviewer cannot approve a scope change for them.
- Do not present fixture tests as real integration acceptance. Verify examples
  using real agents/integrations or state the exact blocker and unfinished work.

- Never add or leave verification-only global turn caps, exhausted experiment
  budgets, or test authorization gates in normal runners or service launchers.
  Bound experiments in a separate harness. Retain historical evidence without
  letting its counters restrict normal user runs. Do not spend model turns solely
  to verify removal of a cap; use explicitly approved live checks when needed.

## Python module cohesion

- Follow [Rule N1 — Recognizable and distinct names](https://github.com/amadou-6e/my-skills/blob/5b4af08/05-software_engineering/skill-code/skill-naming/SKILL.md#rule-n1--recognizable-and-distinct-names)
  when naming or renaming code entities.

- Beneath the `tests/` discovery root, prefix every folder containing tests,
  directly or through nested concerns, with `test_`. Keep support-only and
  data-only folders descriptive. Update discovery, imports and CI paths together.

- Group cohesive features into packages; do not stop at a fixed nesting depth.
  Repeated filename prefixes are a signal to review the package boundary.
- A Python implementation file introduces classes or standalone functions, never
  both. Put class-only exceptions in errors.py. Keep package initializers small.
- Make a function a method when its responsibility belongs to an object. Keep
  independent helpers in the owning feature's utils.py (or a focused function-only
  module); do not create a cross-domain dumping ground of utilities.
- When values repeatedly travel together as one concept, define a canonical
  Pydantic model in that feature's models.py and pass that model internally.
  Put constructors, validation and projections on the model where appropriate.
  Preserve existing external payloads, persisted schemas and error behavior at
  explicit boundaries; do not silently coerce input or duplicate domain models.
- Migrate callers to defining modules and remove obsolete files. Add structural
  regression checks so mixed class/function files and retired imports cannot
  quietly return.

- Import objects directly from their defining modules; avoid module-prefix aliases throughout callers.
- Model large owned configuration records with typed Pydantic objects and explicit `to_config()` projections.
- Define classes at module scope in their owning files; never nest handlers or construct class definitions inside functions.
- Apply these rules to owned/reworked code while preserving standard-library boundaries and immutable historical sources.
- Document module structure and mandatory object nomenclature in its README before implementation; describe leaf object methods and outcomes.
- Group frontend code, tests and assets by concern, separate wire types from rendering, and update deployment/discovery with moves.

## Settings and exception contracts

- Name feature configuration modules `settings.py`, never `constants.py`.
  Externally supplied configuration belongs to a feature-owned Pydantic settings
  object in that file. Load it at the point of use; preserve existing environment
  names, missing/empty behavior and flag semantics. Fixed protocol/security values
  and mutable locks remain single-owner values, not configurable fields.
- Keep credentials out of settings serialization and representations. Preserve
  explicit child-process environment filtering, dynamic credential lookups and
  standard-library-only credential helpers.
- Exceptions in `errors.py` must document their distinct domain and outcome
  guarantees and expose the existing stable machine `code`. Preserve inheritance,
  exception arguments and boundary categories. Specialized subclasses may inherit
  the implementation but must document their contract; do not leave pass-only
  placeholders. User-facing explanations/recovery belong to the shared catalogue.

## Commit and push checkpoints

- After each coherent, reviewable block of work, commit and push the task branch
  promptly. Do not accumulate several completed blocks locally or wait until the
  whole task, final review or live verification is finished before pushing.
- Push in-progress work to a draft branch/PR with its pending checks and blockers
  stated clearly. A pushed checkpoint is not a verification or completion claim,
  and it does not authorize merging.
- Stage only changes owned by the task. Preserve unrelated edits; never commit
  credentials, private runtime state, generated caches or verification tooling.

## Issue and branch ownership

Follow the canonical [specs GitHub workflow](https://github.com/amadou-6e/specs/blob/main/AGENTS.md).
Identify or create the owning issue before branching; use exactly `<type>/<issue-number>`
with `feat`, `fix`, `docs`, `chore` or `refactor`. Link each PR to its owning issue.
Existing issue title/body/label/state edits and closure require explicit approval.
Do not add closing keywords without that approval. Push coherent blocks to the
owning issue branch, keep its draft PR current and preserve review/evidence limits.
