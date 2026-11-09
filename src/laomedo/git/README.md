# Shared host Git mechanics

This package owns bounded host Git commands, isolated environments and native
repository/working-tree operations. Authorization, source admission, GitHub refs,
Agent workspace policy and publication decisions belong to callers.

| Defining module | Object | Concern and method vocabulary |
| --- | --- | --- |
| `command.py` | `GitCommandRunner` | `run(command)` executes once; `isolated_home(profile)` owns a private sequence home; `environment(command, home)` projects child variables |
| `repository.py` | `GitRepository` | `run`, `init_bare`, `fetch`, `object_type`, `is_ancestor`, `changed_paths`, `resolve`, `check_ref_format`, `fsck` provide native metadata mechanics |
| `worktree.py` | `GitWorkingTree` | `clone_from`, `checkout_detached`, `index_entries`, `status_porcelain`, `sparse_enabled`, `remove_remote`, `remotes` manage admitted working state |
| `models.py` | `GitCommand`, `GitExecutionContext`, `GitCredential`, `GitEnvironmentProfile` | Canonical Pydantic command/isolation values; credentials and environment overrides excluded from ordinary dumps and reprs |
| `errors.py` | `GitOperationError`, `GitCommandTimeout` | Safe operation code or deadline with a separate `cleanup_verified` observation |
| `settings.py` | Fixed protocol values | Thirty-second default, five-second cleanup substep bound and private credential variable name |
| `credential_helper.py` | Standard-library helper | GitHub-only credential projection for the selected connection, independently executable by Git |

Runner means native execution, Repository means object metadata, and WorkingTree
means checked-out state. Objects compose; none grants a remote effect. Feature
interfaces import defining symbols directly. There is no generic feature registry.

## Isolation and errors

WORKSPACE and HOST_TRANSPORT strip inherited Git/GCM and host GitHub overrides,
isolate HOME/USERPROFILE/XDG_CONFIG_HOME, and remove HOMEDRIVE/HOMEPATH. WORKSPACE
closes stdin, disables optional locks and skips LFS smudging. HOST_TRANSPORT keeps
its established stdin behavior and disables prompting. Selected tokens enter only
the private child credential environment, never argv or normal model dumps.

Every command uses a bounded process group/tree and bounded cleanup waits. A
GitCommandTimeout is a subprocess.TimeoutExpired with cleanup_verified; cleanup
does not prove whether a remote operation happened. GitHub retains unknown-effect
classification and must not blindly retry. Agent workspace preparation and remote
configuration map timeouts to their existing GitWorkspaceError codes; Skill
baseline initialization maps startup/timeout failures to its own existing code.
Verified publication uses strict private-home cleanup; transport preserves its
established tolerant private-home policy. The caller owns its selected timeout.

## Scope and consumers

The boundary serves Agent Git preparation, mediated remote configuration, Skill
baseline initialization, GitHub transport and verified publication staging.
Credential-free source discovery in `skills/sources/repository.py` owns a separate
read-budget process path and is outside this API. No read profiles, output budgets
or Windows read-containment extension are exposed here.

`GitHubGitTransport`, `VerifiedGitStage` and `stage_verified_git` accept a
GitCommandRunner through `runner=`. The former subprocess-shaped `run=` callback
is unsupported: callers must migrate explicitly; there is no callable adapter or
second production process path. Retired procedural environment/argv helpers also
require manual migration. Archived execution evidence retains its original bytes;
only explicitly identified migrated copies may execute against the new interface.

The flat credential_helper.py remains independently executable using only the
standard library. Git receives the admitted credential through its private
process environment; helper protocol output must never be logged as diagnostics.
