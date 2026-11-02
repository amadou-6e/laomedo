# Agent working state

This package owns Agent working-copy admission and preparation.
`prepare_git_workspace` in `git.py` prepares controlled checkouts using the shared
Git boundary. `settings.py` owns admission constants and `errors.py` owns
`GitWorkspaceError`.

The skills/ leaf owns run-local Skill installation and exclusion of those files
from the Agent's repository changes. It consumes general immutable Skill records;
the Skill registry does not depend on Agent workspace preparation.
