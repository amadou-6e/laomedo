# Examples

Start with [Skills](skills/README.md) for selecting and inspecting immutable
instructions and building an atomic-edit graph with the existing Agent.
The [Skill walkthrough](../docs/features/skills/walkthrough.md) gives complete
local service setup and describes the optional real execution.

The maintained Skill entrypoint contains one builder and its real editor skill.
Historical executed exports and campaign variants are preserved on `exp`, with
original revisions and byte provenance; they are not current setup instructions.

Other folders own provider-specific and GitHub graph workflows.
`skill-agent-pilot` retains the historical Agent runner prototype and its Agent
test assets. `skill-files-viewer` and `skill-summary` retain the files and evidence
of their named campaigns; the Skill walkthrough documents current setup and
behavior. The maintained Skill builder does not import these campaign scripts.
