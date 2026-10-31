# EXP-08: exact skill bytes and workspace cleanliness

This bounded, credential-free probe addresses
[issue #38](https://github.com/amadou-6e/laomedo/issues/38). It imports one
whole skill as an immutable `SkillStore` revision and invokes the runner's
materialization method in two disposable **Git clones**. It does not
dispatch an agent or make a model call.

```text
python -m experiments.exp08.probe
python -m unittest experiments.exp08.test_probe
```

Neither normal command rewrites the committed evidence. Run
`python -m experiments.exp08.probe --record` only when intentionally
refreshing it; the output is written with LF bytes.

Both LF and CRLF `SKILL.md` fixtures are tested as distinct byte revisions.
The [sanitized observation](observation.json) records exact source,
effective, and post-edit hashes. Source/effective skill bytes match on
materialization; editing the effective copy changes only its hashes. The
canonical revision and source Git tree stay unchanged through cleanup. Before
the skill is ignored, an unprotected clone shows it in `git status`,
`git add -A`, and `git clean -nd`. In the protected clone,
`.git/info/exclude` keeps it out of status, add-all, and ordinary clean
dry-runs. `git clean -ndx` would still remove it: force-clean is not safe
without rematerialization. Git's LF-to-CRLF checkout conversion is exercised
on a tracked fixture, while delivered skill bytes remain exact. A
parent-path read, unsafe skill ID and tampered stored revision are rejected
before the latter reaches an effective workspace.

The expected path is `.agents/skills/exp08-sample/SKILL.md`, but native
Codex discovery is **unverified**. The runner reports the skill as
`offered`, not read or used. A model-backed discovery test needs a separate
explicit turn cap and authorization. This probe does not validate Docker
mounts, actual session behavior, or all filesystem links/reparse-point cases.
The temporary clone's local exclude rule is a test of the intended behavior,
not proof that the production runner installs that rule.
