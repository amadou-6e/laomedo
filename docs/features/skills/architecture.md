# Skill architecture

The [Skill component](../../../components/laomedo/skill.py) is the graph boundary.
`src/laomedo/skills/` owns authoring, ingestion, inspection, operations, registry,
sources and workspace concerns. Packaged skill files belong to that feature's
resources. See [package layout](../../architecture/package-layout.md).

The [registry](registry.md) separates immutable revisions from editable drafts
and makes promotion a separate checked operation. Editing policies and revision
hashes bind the reviewed proposal to its base; an Agent edit is not automatically
a promoted revision. Agent execution is described under [Agents](../agents/README.md).

Source discovery and operation services remain within Skills. GitHub issue and
PR mutations belong to [GitHub](../github/README.md), rather than the skill store.
