# Project storage

`ProjectStorage` owns profile-scoped checkout registrations, graph file bindings and
the general agent-files location. `ProjectRepositories.clone()` clones an explicitly
selected GitHub repository into app-owned storage and registers it only after a
successful checkout. An optional read token is used once by the private Git helper;
it is never retained in metadata or passed to the native agent. Neither object
commits or pushes. `RepositoryClone` is the browser request, not an MCP tool input.
`StorageDocument` is the persisted configuration; `RepositoryLocation` identifies a
registered checkout and a relative path. HTTP settings use authenticated profile
authority. MCP list/read/write methods use the active chat authority already checked
by `AuthoringMcp`. Graph files are read-only to those tools.

`register()` verifies an existing local checkout. `configure_agent_files()` selects
an explicit subtree. `read_file()` and `write_file()` operate only in that subtree;
write uses an observed SHA-256 or an absent-file condition. `graph_path()` checks a
separate per-graph location. `save_document()` atomically replaces app-owned metadata.
No native provider receives a host path, credential file or unrestricted mount.

`ProjectChatWorkspace.prepare(owner, conversation)` freezes the selected agent
folder and graph files into `WorkspaceFiles` on the first dispatch. The shared
runner copies those bounded UTF-8 files into `/draft/project/agent-files/` and
`/draft/project/graphs/<graph-id>.json`. Subsequent turns resume that same native
workspace. Changing storage settings applies to new conversations; it does not
retarget an existing chat. The initial bundle is retained for idempotent retries.
MCP file tools use those same frozen locations, including an initially empty
selection. They read current repository contents, not the native workspace copy.

`persist(owner, conversation, files)` reads the runner's verified completed
snapshot and writes changed files back only when each host file still matches its
observed hash and the dispatching browser session is still authorized. The host-only
session fingerprint is refreshed for each admitted turn and never enters native
files or model payloads. New agent files and deletions are included. Unknown graph paths,
secret filenames, links, binary files and oversized bundles are refused. Graph
file edits do not change app graphs until explicit Load. Conflicts retain the
native snapshot and show an error while unlocking Send; external edits are never
overwritten. File replacements are individually atomic; multiple replacements
are not a distributed transaction. An interrupted or failed turn is not exported.
On a conflict, use `read_project_file` to inspect the current repository version,
then restore that exact text in the native workspace on the next turn. Identical
contents safely update the baseline without overwriting the repository; a later
turn can edit normally. Remove unsupported paths or non-UTF-8 files from the native
`project/` tree before retrying. Preflight failure writes no selected files. Send
remains available, and recovery does not require a new conversation. Byte decoding
preserves CRLF in files that the model does not deliberately normalize.
The bundle is limited to 256 files and 256 KiB serialized JSON. This is selected
file access, not a mount of the entire repository or its Git metadata.

This pilot supports explicit graph save/load, not editor autosave synchronization.
Portable graph files omit app-managed settings and component code. App state remains
available when a checkout is offline. Diff review and remote synchronization follow.
