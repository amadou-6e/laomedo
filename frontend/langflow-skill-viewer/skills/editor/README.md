# Working files and publication

`useSkillEditing` owns working buffers, undo/redo and exact pending save/publication identity. `useRegistryComparison` compares the cumulative candidate to the registry. `SkillSourceEditor` owns Monaco models, workers, selection and disposal; previews and confirmation dialogs have no write authority.
