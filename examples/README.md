# Examples

Start with [Skills](skills/README.md) for selecting and inspecting immutable
instructions and building an atomic-edit graph with the existing Agent.
The [Skill walkthrough](../docs/features/skills/walkthrough.md) gives complete
local service setup and describes the optional real execution.

The maintained Skill entrypoint contains one builder and its real editor skill.
Historical executed exports and campaign variants are preserved on `exp`, with
original revisions and byte provenance; they are not current setup instructions.

Agent and GitHub examples retain their current folders pending their separate
organization pass. In particular, `skill-agent-pilot` is a historical Agent runner
prototype with active Agent-test consumers, so it stays here. `skill-files-viewer`
and `skill-summary` were not touched by this PR and remain outside this scoped
consolidation. This index does not claim all examples have been reorganized.
