# Verified publication

This concern admits immutable publication evidence and stages only its verified
bundle. It owns grant/run correlation, byte hashes, fixed refs, verification and
publication policy. Generic Git execution is composed from `laomedo/git`.

| Object | Responsibility and nomenclature |
| --- | --- |
| `VerifiedStage` | Canonical immutable snapshot and its verified scope; a data model, not an execution grant. |
| `VerifiedGitStage` | Temporary Git object store imported from that snapshot, never from the mutable Agent checkout. |

| Interface | Behavior |
| --- | --- |
| `resolve_verified_stage(...)` | Resolve exact retained bytes against trusted run/grant scope and verification evidence. |
| `stage_verified_git(snapshot, *, runner=None)` | Own the disposable object store and yield `VerifiedGitStage`; delete it on context exit. |
| `classify_workflow_change()` | Inspect that exact object's history and apply the shared GitHub workflow-path rule. |
| `repository` | Composed `GitRepository` used by import and classification; later publication must use this same `bare` directory while the stage is alive. |

The old duplicate Git process adapter is removed. Timeouts/startup failures keep
`stage_git_unavailable`; invalid snapshot/import/history/diff retain their existing
codes. A staged object store is neither provider authorization nor proof of a push.
