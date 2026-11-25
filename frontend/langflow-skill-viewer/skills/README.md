# Skill frontend

The viewer is divided by responsibility, with one canonical file/revision model
in `models.ts`. `interface/` is the entry point for the wider Langflow app;
`workspace/` composes the view; `editor/` owns working state and publication;
`explorer/`, `history/` and `search/` own their respective navigation surfaces.
`node/` adapts the graph node controls and has a separate upstream destination.

Component names identify visible objects; `use*` names identify stateful hooks.
Pure working-tree functions stay in `SkillWorkingTree.ts`. Commit, Snapshot and
SkillFile are shared wire contracts, not view-owned models. Components consume
those contracts rather than importing their types from another component.

Tests sit beside their owning module and use fresh local state. They are internal
controls; real browser stories are required for workflow acceptance. Deployment
preserves these package boundaries under Langflow's skillFilesModal directory;
the node adapter is copied to upstream input rendering. No legacy forwarding
files remain at the overlay root.

`private/` owns explicit connection-bound read-only discovery and viewing.
`interface/selection.ts` keeps private selections bound to connection and source;
`SkillViewer` routes them directly to `PrivateSkillViewer`, bypassing public edit,
publication and inspection hooks. Node Advanced settings includes
`PrivateSkillControls`. Private graphs grant no Agent materialization authority.

## Keyboard and failure boundaries

Source text and navigation keys reach Monaco without triggering canvas shortcuts.
Workspace Ctrl+F opens Find; Escape closes active Find or transient controls before
the dialog. The viewer remains above transient toolbars during canvas refresh.
Inspection failure parsing accepts only response `data.code` or `detail.code`.
Immutable refusals have no futile reload; unknown read failures can reload only
the same read. Credential-shaped identifiers and raw response bodies never become
user-visible diagnostics. These are regression requirements, not acceptance claims.
