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
test assets. The earlier Skill-only campaigns are preserved on
[`exp` at their retained revision](https://github.com/amadou-6e/laomedo/tree/a45dd257361358279328711a0ccde8fac369dac2/examples).
The Skill walkthrough documents current setup and behavior; the maintained
builder does not import campaign scripts or require an experiment checkout.
