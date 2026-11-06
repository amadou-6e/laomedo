# Skill file actions

The explorer groups files by folder. Type icons distinguish Markdown, JSON and
other supported files; Codicon chevrons indicate disclosure independently from
selection. Icon attribution is in the [bundled notice](../../../frontend/langflow-skill-viewer/skills/assets/skill-icons-NOTICE.txt).

Right-click a file, folder or empty explorer space to open its applicable menu.
Upload accepts multiple text or binary files as one batch. Dropping local files
imports them; dragging an existing row moves it. Destinations use grey highlighting.
Ctrl+X and Ctrl+V provide keyboard movement; there is no Move to menu.

Rename edits the filename directly in its row. Enter accepts; Escape cancels.
Delete removes immediately. With focus in Files, Ctrl+Z restores a file action
and Ctrl+Y reapplies it. Copy relative path copies the portable registry path.
Deleting or moving the last child leaves an empty working folder visible.
Creating an empty file or folder directly is not a supported menu action.

Imports validate all names, collisions, sizes and permissions before changing
any working file. Failed batches preserve the previous working copy. Renames
and moves retain exact bytes and text buffers. Publish applies the complete batch.

Recognized raster formats preview inside the available editor pane. Other binary
files use a bounded paged byte view; neither shows a byte/hash header. SVG and PDF
are never executed or embedded. Binary content editing is unsupported.
