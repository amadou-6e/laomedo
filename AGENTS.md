# Contributor instructions

- Before merging any PR, use the Claude reviewer workflow at
  `../specs/shared/skills/claude-reviewer/SKILL.md` (the canonical specs repository).
  Review the full substantive diff against its intended base, including earlier
  commits. Prepare exact base/head revisions, applicable specifications and checks.
- Reuse the workflow's reviewer session for the current Codex conversation.
  The reviewer is read-only; it cannot publish, mutate issues, or run model probes.
- Address confirmed findings and run affected checks. Obtain the prescribed
  focused recheck for blocking findings. Record reviewed revisions and the verdict.
  Merge only with resolved review blockers and passing required checks.
- Do not present fixture tests as real integration acceptance. Verify examples
  using real agents/integrations or state the exact blocker and unfinished work.
