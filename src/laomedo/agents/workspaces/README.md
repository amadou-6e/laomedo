# Agent working state

This concern owns Agent source admission and immutable file snapshots. Generic
Git commands, process isolation and cleanup live in `laomedo/git`; authorization
and protected-file policy remain with their existing callers.

| Object | Responsibility and nomenclature |
| --- | --- |
| `AgentWorkspace` | Agent-qualified owner of working-state preparation; composes Git mechanics, not an inheritance variant for each storage mode. |
| `WorkspacePaths` | Canonical source/directory pair, retained privately rather than repeatedly passing paths. |
| `WorkspaceSnapshot` | Preparation result: canonical source hash and optional trusted Git baseline. |
| `GitWorkspaceError` | Existing admission/cleanup codes; a failed preparation never grants dispatch. |

| Method | Interface and effects |
| --- | --- |
| `prepare(canonical, *, git)` | Prepare the run directory and canonical snapshot; return `WorkspaceSnapshot`. Git mode preserves history; directory mode copies admitted files. |
| `prepare_git()` | Admit a clean trusted repository root, clone independent objects, detach its observed baseline and remove remotes. Return that baseline. |

`utils.py` owns independent tree hashing/copy functions shared by preparation,
existing restore and post-run verification. Restore/protected-state transitions
still belong to `BaseAgent`; extracting those later is not implied by this move.
The object is not a namespace replacement for generic Git operations. Sources
must be trusted host input, never prior Agent output. Existing symlink, gitlink,
sparse, tracked-skill, dirty-source and cleanup refusals remain in force.
