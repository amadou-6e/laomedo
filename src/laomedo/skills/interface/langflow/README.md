# Langflow Skill components

`SkillComponent` owns shared Skill reference, revision and operation behavior.
The catalog exposes separate `LaomedoLocalSkill` and `LaomedoGitHubSkill`
components: the former accepts local folders and snapshots current files without
exposing revision or commit controls; the latter
accepts GitHub and public GitLab repository URLs, with an optional GitHub
connection for private reads. Each component validates its source type before
discovery or execution. Private reads retain their existing read-only boundary.
