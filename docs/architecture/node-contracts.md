# Node responsibilities and boundaries

The graph composes domain nodes rather than giving the Agent every integration's
settings. Component definitions live in [components/laomedo](../../components/laomedo).

| Feature | Responsibility | Implementation guides |
| --- | --- | --- |
| Agents | Dispatch agent work, retain run identity and expose activity | [Agents](../features/agents/README.md) |
| Skills | Resolve skill revisions and validate multi-file edit proposals | [Skills](../features/skills/README.md) |
| GitHub | Select repository work and execute authorized issue or PR operations | [GitHub](../features/github/README.md) |

The PR feedback example routes PR context into an existing Agent and returns an
operation to the same PR node. The host validates the operation and authorization
before applying it; the Agent's proposal alone is not proof of a GitHub update.
See the [PR workflow](../../examples/github-pr/README.md) for the supported
feedback wiring and its limitations.

Skill editing similarly separates a proposed file change from controlled revision
promotion. See the [registry guide](../features/skills/registry.md). Provider
execution and retained activity remain Agent concerns, while credential-bearing
services stay on the trusted host.

This page is an implementation map, not a replacement payload schema. Consult
the owning components, feature guides and
[canonical shared contracts](https://github.com/amadou-6e/specs/blob/main/projects/laomedo/architecture/shared-contracts.md)
when changing a boundary.
