# Contributor instructions

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

## Commit and push checkpoints

- After each coherent, reviewable block of work, commit and push the task branch
  promptly. Do not accumulate several completed blocks locally or wait until the
  whole task, final review or live verification is finished before pushing.
- Push in-progress work to a draft branch/PR with its pending checks and blockers
  stated clearly. A pushed checkpoint is not a verification or completion claim,
  and it does not authorize merging.
- Stage only changes owned by the task. Preserve unrelated edits; never commit
  credentials, private runtime state, generated caches or verification tooling.
