# Skill workspace controls

This package protects immutable Skill delivery into an owned working copy. It
uses the actual registry, materialization boundary and shared Git command runner
without starting Docker, a provider or an Agent turn. It replaces the production
dependency on the historical EXP-08 campaign; the original remains on `exp`.
Its [original files and provenance](https://github.com/amadou-6e/laomedo/tree/3e5f7d7e9e2de9c291da44f87cdc0cf809fa524a/archives/experiments/exp08)
retain their historical limitations and do not certify native Skill discovery.

`SkillMaterializationTests` owns temporary source, registry and Git clones.
`prepare()` creates a fresh case for the supplied line ending. `git()` executes
only fixture-local Git commands through the shared isolated command boundary and
raises on failure. Tests assert exact bytes, LF/CRLF revision distinction, edit
isolation, Git add/clean behavior, path rejection and tampered-revision refusal.
These are internal regression checks, not native Skill discovery acceptance.

Run with the installed package:

```powershell
python -m unittest discover -s tests/skills/workspace -t tests -v
```
