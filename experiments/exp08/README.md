# EXP-08: exact skill bytes and workspace cleanliness

This bounded, credential-free probe addresses
[issue #38](https://github.com/amadou-6e/laomedo/issues/38). It imports one
whole skill as an immutable `SkillStore` revision and invokes the runner's
materialization method in a disposable effective workspace. It does not
dispatch an agent or make a model call.

```text
python -m experiments.exp08.probe
python -m unittest experiments.exp08.test_probe
```

Both LF and CRLF `SKILL.md` fixtures are tested as distinct byte revisions.
The [sanitized observation](observation.json) records exact source,
effective, and post-edit hashes. Source/effective skill bytes match on
materialization; editing the effective copy changes only its hashes. The
canonical revision and source Git tree stay unchanged through cleanup. A
parent-path read, unsafe skill ID and tampered stored revision are rejected
before the latter reaches an effective workspace.

The expected path is `.agents/skills/exp08-sample/SKILL.md`, but native
Codex discovery is **unverified**. The runner reports the skill as
`offered`, not read or used. A model-backed discovery test needs a separate
explicit turn cap and authorization. This probe does not validate Docker
mounts, actual session behavior, or all filesystem links/reparse-point cases.
