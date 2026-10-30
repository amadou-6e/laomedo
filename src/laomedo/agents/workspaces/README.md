# Agent working state

This concern owns Agent source admission, independent working directories,
immutable snapshots and run-local skill integrity. Reusable native Git commands,
process isolation and process-tree termination belong to `laomedo/git`.
Repository authorization and protected-file policy stay with their callers.

The focused helper ownership below is the D3 README-first target. The helper
relocation has not yet been implemented in this documentation checkpoint.

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
| Independent file-tree operations | `utils.py` | Existing hashing/copy functions for preparation, restore and verification |

Workspace names working state, Paths its source/directory binding, and Snapshot
the preparation observation. AgentWorkspace is an actual preparation owner, not
a namespace for all Git operations or a Base with no abstract responsibility.
Baseline and cleanup remain functions: failure cleanup can be needed before a
workspace object has been constructed. No artificial lifecycle object is needed
to call either function. The shared Git runner remains their native process owner.

## Object and function interfaces

| Interface | Effects and preserved guarantees |
| --- | --- |
| `AgentWorkspace.prepare(canonical, *, git)` | Prepare the run directory and canonical snapshot; return WorkspaceSnapshot. Git mode preserves admitted history; directory mode copies admitted files. |
| `AgentWorkspace.prepare_git()` | Admit a clean trusted repository root, clone independent objects, detach its observed baseline and remove remotes. |
| `initialize(workspace)` | Refuse pre-existing Git metadata; create the existing independent baseline through GitRepository/GitCommandRunner. Never copy host Git metadata or hooks. |
| `remove_owned_tree(path, state)` | Refuse the state root, an outside path or a linked target; retain existing read-only-file retry admission and removal behavior. |

Restore/protected-state transitions still belong to BaseAgent. Sources must be
trusted host input, never prior Agent output. Existing symlink, gitlink, sparse,
tracked-skill, dirty-source and cleanup refusals stay in force. Historical
WorkspaceSkillError covers baseline/cleanup as well as skill verification;
this relocation does not reclassify it or change its translation to RunnerError.

The [skill delivery README](skills/README.md) identifies its canonical records
and exact function vocabulary. The old general Skills workspace package is
removed when this relocation is implemented. Known helper imports migrate to
their defining functions; a split namespace is not recreated by a facade.
