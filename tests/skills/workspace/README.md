# Skill workspace controls

This package protects immutable Skill delivery into an owned working copy. It
uses the actual registry, materialization boundary and shared Git command runner
without starting Docker, a provider or an Agent turn. The historical EXP-08
campaign is retained separately on `exp`.
Its [original files and provenance](https://github.com/amadou-6e/laomedo/tree/3e5f7d7e9e2de9c291da44f87cdc0cf809fa524a/archives/experiments/exp08)
retain their historical limitations and do not certify native Skill discovery.

`test_exclusion.py` checks installed exclusions, independent cleanup and refusal
paths through the runner integration. It uses the shared `FakeServer` from the
Agent tests for protocol responses; fixture state is isolated per scenario.

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
