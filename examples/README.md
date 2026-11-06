# Examples

Start with [Skills](skills/README.md) for selecting and inspecting immutable
instructions and building an atomic-edit graph with the existing Agent.
The [Skill walkthrough](../docs/features/skills/walkthrough.md) gives complete
local service setup and describes the optional real execution.

The maintained Skill entrypoint contains one builder and its real editor skill.
Historical executed exports and campaign variants are preserved on `exp`, with
original revisions and byte provenance; they are not current setup instructions.

Other folders own provider-specific and GitHub graph workflows.
Start GitHub work with the [single GitHub builder](github/README.md): existing
Issue/PR inspection and bounded PR feedback through a real Agent. Historical
GitHub campaigns and fixture examples are archived on `exp`; their tests do not
serve as live workflow acceptance. `graph.py` provides pure shared node/edge
construction for the maintained Skill and GitHub builders.
The Agent runner prototype and its test dependencies remain Agent-owned until
that migration. Skill viewer and summary campaigns are archived on `exp`; use
the maintained Skill walkthrough for current setup. Historical evidence links
in the product documentation identify an immutable archive revision and do not
claim acceptance of the current UI. The maintained Skill builder imports no
campaign scripts.
