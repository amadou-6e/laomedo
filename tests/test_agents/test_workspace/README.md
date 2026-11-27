# Workspace controls

Existing Agent regressions for this concern. Run `python -m unittest discover -s tests/test_agents -t tests -v`. Internal controls do not establish real provider acceptance.

`test_skill_exclusion.py` owns runner exclusion, independent cleanup and refusal
before reading unsafe Skill metadata. It uses the shared transport control and
retains the baseline-inventory refusal assertion; Skills has no duplicate suite.
`test_materialization.py` owns actual local registry/Git preparation, exact bytes,
LF/CRLF distinction, edit isolation, Git add/clean behavior, path rejection and
tampered revisions. It does not start Docker, a provider or an Agent turn.

`SkillMaterializationTests` owns each temporary source, registry and clone.
`prepare()` makes a fresh case for the requested line ending; `git()` runs only
case-local commands through the isolated Git boundary and raises on failure.
Historical EXP-08 sources and provenance remain on `exp`; these maintained
assertions establish internal regression coverage, not native Skill discovery.

`test_guards.py` owns symmetric sandbox guard preparation in Git and directory
mode, unchanged original sources, protected-content refusal, actual junction/link
rejection, and unchanged defaults for other providers. `WorkspaceGuardTests`
creates only disposable local source repositories; `_prepare` returns the
prepared copies and snapshot, and `_init_git` creates a case-local baseline.
These controls do not submit model tasks or establish live review acceptance.
