# Project storage

`ProjectStorage` owns profile-scoped checkout registrations, graph file bindings and
the general agent-files location. It never clones, runs Git, commits or pushes.
`StorageDocument` is the persisted configuration; `RepositoryLocation` identifies a
registered checkout and a relative path. HTTP settings use authenticated profile
authority. MCP list/read/write methods use the active chat authority already checked
by `AuthoringMcp`. Graph files are read-only to those tools.

`register()` verifies an existing local checkout. `configure_agent_files()` selects
an explicit subtree. `read_file()` and `write_file()` operate only in that subtree;
write uses an observed SHA-256 or an absent-file condition. `graph_path()` checks a
separate per-graph location. `save_document()` atomically replaces app-owned metadata.
No native provider receives a host path, credential file or unrestricted mount.

This pilot supports explicit graph save/load, not editor autosave synchronization.
Portable graph files omit app-managed settings and component code. App state remains
available when a checkout is offline. Diff review and remote synchronization follow.
