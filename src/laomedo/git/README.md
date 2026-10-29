# Shared Git mechanics

One owner for reusable host Git mechanics. The initial relocation puts the
standard-library-only credential helper under `credentials/helper.py`; generic
`GitCommandRunner`, `GitRepository` and `GitWorkingTree` are the next extraction.
Their presence is not implied by this README.

| Target object | Responsibility / method vocabulary |
| --- | --- |
| `GitCommandRunner` | Controlled command execution, deadlines and process-tree cleanup; `run` returns a process result or explicit timeout uncertainty. |
| `GitRepository` | Repository mechanics: inspect, clone, fetch and remote operations as actually needed by callers. |
| `GitWorkingTree` | Checked-out file state: checkout, status and commit operations as actually supported. |

No caller authorization moves here: Agent admission stays in workspaces, GitHub
request/push policy in its transport, grants/credentials in trusted host services.
Never route normal model-side container Git to host execution through these objects.
Centralization must replace both existing process runners, with caller-specific
stable error translation and exact cleanup behavior preserved.
