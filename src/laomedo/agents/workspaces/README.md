# Agent working state

This concern owns Agent source admission, independent working directories,
immutable snapshots and run-local skill integrity. Reusable native Git commands,
process isolation and process-tree termination belong to `laomedo/git`.
Repository authorization and protected-file policy stay with their callers.

## Concerns and nomenclature

| Concern | Defining owner | Object or function vocabulary |
| --- | --- | --- |
| Working-state preparation | `workspace.py` | `AgentWorkspace`: `prepare`, `prepare_git`; compose generic Git mechanics |
| Source and run directory | `models.py` | `WorkspacePaths`; one admitted source/directory concept |
| Preparation evidence | `models.py` | `WorkspaceSnapshot`; source hash and optional observed Git baseline |
| Independent directory-mode baseline | `baseline.py` | `initialize(workspace)`; create private Git metadata with deterministic initial identity |
| Owned failed-run removal | `cleanup.py` | `remove_owned_tree(path, state)`; refuse paths outside owned run state |
| Run-local skill exclusion and integrity | `skills/utils.py` | `_exclude`, `install`, `verify`; existing signatures and record shapes |
| Admission and preparation failures | `errors.py`, `skills/errors.py` | Existing `GitWorkspaceError`, `WorkspaceSkillError`; code/args/inheritance preserved |
| Independent file-tree operations | `utils.py` | Hash and copy complete trees; reject unreadable directories instead of silently omitting them |
| Verified change projection | `changes.py` | `verified_changes`: derive a bounded text patch only from matching immutable snapshots |

Workspace names working state, Paths its source/directory binding, and Snapshot
the preparation observation. AgentWorkspace is an actual preparation owner, not
a namespace for all Git operations or a Base with no abstract responsibility.
Baseline and cleanup remain functions: failure cleanup can be needed before a
workspace object has been constructed. No artificial lifecycle object is needed
to call either function. The shared Git runner remains their native process owner.

## Object and function interfaces

| Interface | Effects and preserved guarantees |
| --- | --- |
| `AgentWorkspace.prepare(canonical, *, git, guard_directories=())` | Prepare the run directory and canonical snapshot; return WorkspaceSnapshot. Git mode preserves admitted history; directory mode copies admitted files. Provision provider-owned empty sandbox guard directories in both copies before their final hashes. Never change the original source, replace existing entries or import credentials. |
| Workspace filesystem failures | Report `workspace_access_failed` without exposing private paths; no incomplete source snapshot is accepted. |
| `verified_changes(canonical, post_run, *, source_hash, post_run_hash, imported_artifacts)` | Recheck snapshot hashes before and after a deterministic patch; refuse imports, directory or mode changes, protected paths, binary files and oversized changes. Bound each full tree at 10,000 entries and 64 MiB, changed files at 32 and 1 MiB each, and the patch at 12,000 bytes. Snapshot hashes cover names and content, not file modes; mode detection depends on the host filesystem. The caller must guarantee no process can mutate snapshots while this projection runs. |
| `AgentWorkspace.prepare_git()` | Admit a clean trusted repository root, clone independent objects, detach its observed baseline and remove remotes. |
| `initialize(workspace)` | Refuse pre-existing Git metadata; create the existing independent baseline through GitRepository/GitCommandRunner. Never copy host Git metadata or hooks. |
| `remove_owned_tree(path, state)` | Refuse the state root, an outside path or a linked target; retain existing read-only-file retry admission and removal behavior. |

Restore/protected-state transitions still belong to BaseAgent. Sources must be
trusted host input, never prior Agent output. Existing symlink, gitlink, sparse,
tracked-skill, dirty-source and cleanup refusals stay in force. Historical
WorkspaceSkillError covers baseline/cleanup as well as skill verification;
callers translate it to RunnerError without changing the refusal code.

Codex pins its native sandbox's `.aws` and `.codex` guard directories in its
provider settings. `AgentWorkspace._prepare_guards` admits real directories only;
existing contents are preserved, while files, links and reparse points are
refused. The canonical source hash includes these prepared directories (the
original source hash is checked during copying). Other providers request none.
Resume retains the original immutable canonical snapshot and rechecks the
workspace/post-run hashes; it never retrofits or rewrites old snapshots.
The change projector still rejects directory changes and protected file changes,
including anything below these guards. Hashing still rejects links, reparse
points and hard-linked files; there is no ignored sandbox-directory exception.

The [skill delivery README](skills/README.md) identifies its canonical records
and exact function vocabulary. Callers import these defining owners directly;
general Skill registry operations remain in the Skills package.
