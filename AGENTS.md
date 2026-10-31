# Contributor instructions

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

- Apply these conventions to new and reworked code within the owned task. Record
  existing violations for the planned refactor; do not launch an unrelated
  repository-wide or test-suite rewrite merely by adding these instructions.
- Group cohesive features into packages; do not stop at a fixed nesting depth.
  Repeated filename prefixes are a signal to review the package boundary.
- A Python implementation file introduces classes or standalone functions, never
  both. Put class-only exceptions in errors.py. Keep package initializers small.
- Import the classes, functions and other symbols you use directly from their
  defining modules. Prefer `from ...errors import HandoffError` followed by
  `HandoffError(...)`; do not spread aliases such as `_handoffs_errors` and
  `_handoffs_errors.HandoffError(...)` through callers. Use a descriptive symbol
  alias only for a real name collision. Preserve necessary optional-import
  boundaries and update affected patch targets when changing import bindings.
  If a direct import exposes a cycle, correct the dependency boundary or import
  the symbol at its safe point of use instead of spreading module-prefix aliases.
- Extract large configuration/definition literals into typed Pydantic objects in
  the owning feature's `models.py`. Pass the varying inputs into the object and
  let an explicit method such as `to_config()` construct the external dictionary.
  Preserve the exact wire shape, defaults, validation and error behavior. Use
  nested models for independently meaningful nested data; do not hide an opaque
  `dict[str, Any]` behind a model. Keep secrets out of normal dumps and reprs;
  an explicitly privileged native-config serializer may reveal only what its
  private destination requires, and its output must never be logged.
- Define classes at module scope in their own cohesive files. Never define a
  request handler, model, exception or other class inside a method/function, or
  hide it in a class factory. For example, put `BrokerRequestHandler` in
  `http/handler.py` and its server in `http/server.py`, with explicit instance
  references for shared state instead of closure capture or mutable globals.
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

## GitHub issue and branch workflow

- Follow the [canonical GitHub workflow](https://github.com/amadou-6e/specs/blob/main/AGENTS.md#change-workflow).
  Task branches use exactly `<type>/<issue-number>`, with only `feat`, `fix`,
  `docs`, `chore`, and `refactor`. The number is an actual issue in this repository;
  do not append descriptive slugs or invent review/validation/checkpoint prefixes.
- Identify the issue owning the user-selected work, or create it before branching.
  Link each PR to its issue and keep checkpoints and validation on that issue branch.
  A pushed branch alone does not complete the GitHub workflow.
- Existing issue edits and closure require explicit approval; do not use automatic-
  closing PR keywords without it. Preserve the review, CI, and final graph-validation
  gates above. These instructions do not enable GitHub enforcement or rename history.

## Commit and push checkpoints

- After each coherent, reviewable block of work, commit and push the task branch
  promptly. Do not accumulate several completed blocks locally or wait until the
  whole task, final review or live verification is finished before pushing.
- Push in-progress work to a draft branch/PR with its pending checks and blockers
  stated clearly. A pushed checkpoint is not a verification or completion claim,
  and it does not authorize merging.
- Stage only changes owned by the task. Preserve unrelated edits; never commit
  credentials, private runtime state, generated caches or verification tooling.
