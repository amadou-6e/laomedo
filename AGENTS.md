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
