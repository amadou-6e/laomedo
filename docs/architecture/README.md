# Shared architecture

Nodes compose a workflow while feature packages own domain behavior. Agents,
Skills and GitHub have separate responsibilities; host services mediate private
credentials and external effects. Langflow supplies graph composition and the
application integration.

- [Package layout and migration](package-layout.md): source ownership, canonical
  entrypoints, typed internal data and migration from retired module paths.
- [Node boundaries](node-contracts.md): responsibilities and operation exchange.
- [Work Graph foundation](work-graph.md): imported work, immutable snapshots and
  dependency readiness; distinct from the Langflow execution graph.
- Feature owners: [Agents](../features/agents/README.md),
  [Skills](../features/skills/README.md) and [GitHub](../features/github/README.md).

For governing contracts, see the
[canonical architecture](https://github.com/amadou-6e/specs/tree/main/projects/laomedo/architecture).
