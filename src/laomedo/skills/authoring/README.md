# Skill description authoring

This function-only leaf detects missing descriptions and supplies the packaged
authoring instructions for an authorized operation. It does not edit files or
grant authority to the Agent.

| Interface | Responsibility |
| --- | --- |
| `has_description(text)` | Treat unambiguously empty frontmatter values as missing; preserve nonempty or unfamiliar YAML values |
| `summary_authoring(snapshot)` | Require readable `SKILL.md`, then return `summary_required` and `authoring_instructions` |

`has` observes existing text; `authoring` supplies instructions rather than an
edit. The packaged instructions live under `skills/resources/skill-summary/` so
installed wheels and source checkouts use the same content. A missing source
raises `SkillStoreError("skill_summary_source_unavailable")`; the operation HTTP
boundary projects its safe refusal without exposing snapshot bytes or paths.
