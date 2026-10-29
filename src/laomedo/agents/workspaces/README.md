# Agent working state

This concern owns protected files, pinned skills, admission, snapshots and restore
policy for an Agent run. The relocated `git.py` still implements
`prepare_git_workspace(source, destination) -> str`: validate an admitted clean
source, clone without credentials or remotes, and return its verified baseline.

The target behavioral object is `AgentWorkspace`, composing generic Git objects.
Its `prepare`, `verify`, `snapshot` and `restore` vocabulary will describe distinct
state transitions. Those object methods are not implemented by relocation. Do not
create storage-mode subclasses simply to distinguish directory and Git inputs.

Reusable Git commands and process cleanup move to `laomedo/git`; Agent admission
stays here. The source must remain trusted host input, not prior Agent output.
`GitWorkspaceError` retains its current machine codes during extraction. Failed
preparation must report cleanup uncertainty rather than leave an admitted result.
