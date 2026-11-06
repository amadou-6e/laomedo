# Working files and publication

`useSkillEditing` owns working buffers, undo/redo and exact pending save/publication identity. `useRegistryComparison` compares the cumulative candidate to the registry. `SkillSourceEditor` owns Monaco models, workers, selection and disposal; previews and confirmation dialogs have no write authority.

`applySourceChanges(source, changes)` projects Monaco line/column edits onto original text. It preserves a leading BOM and line endings outside replaced ranges; newly inserted separators follow the editor input.
