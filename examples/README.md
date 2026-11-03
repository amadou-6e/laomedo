# Examples

Start with [Skills](skills/README.md) for selecting and inspecting immutable
instructions and building an atomic-edit graph with the existing Agent.
The [Skill walkthrough](../docs/features/skills/walkthrough.md) gives complete
local service setup and describes the optional real execution.

The maintained Skill entrypoint contains one builder and its real editor skill.
Historical executed exports and campaign variants are preserved on `exp`, with
original revisions and byte provenance; they are not current setup instructions.

The [Agent builder](agents/README.md) exports current fresh/resume graphs for all
three providers and provenance handoffs where the component exposes that input.
Its structural checks do not establish live execution acceptance. Historical provider campaigns and execution evidence are preserved on `exp`.
Saved graph compatibility assets belong to concern-owned tests rather than
additional setup entrypoints.

Other folders own GitHub graph workflows.
`skill-agent-pilot` retains the historical Agent runner prototype and its Agent
test assets. `skill-files-viewer` and `skill-summary` retain the files and evidence
of their named campaigns; the Skill walkthrough documents current setup and
behavior. The maintained Skill builder does not import these campaign scripts.
