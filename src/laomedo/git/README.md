# Shared Git mechanics

This package owns host Git execution, repository operations and working-tree
mechanics. Agent admission, GitHub connection selection, source admission and
publication authorization belong to callers. The standard-library-only credential
helper lives in `credentials/helper.py` so Git can invoke it without loading the app.

## Concerns and object nomenclature

| Owner | Object | Responsibility |
| --- | --- | --- |
| `command.py` | `GitCommandRunner` | One native launcher, isolated environments, deadlines, output budgets and process-tree cleanup |
| `repository.py` | `GitRepository` | Object database, refs, remote configuration and fetch mechanics |
| `worktree.py` | `GitWorkingTree` | Clone, checkout and working-state inspection |
| `models.py` | `GitCommand`, `GitExecutionContext`, `GitCredential`, `GitExecutionBudget`, `GitTreeEntry` | Canonical Pydantic execution values, excluded secrets/accounting callbacks and native tree metadata |
| `errors.py` | `GitCommandTimeout`, `GitCommandLimitExceeded`, `GitCommandCleanupError` | Deadline, active-budget refusal and unconfirmed termination |
| [windows/](windows/README.md) | `WindowsProcessTree` | Owned Windows Job Object containment for budgeted reads |
| `settings.py` | Fixed execution values | Credential environment name and cleanup bound; no authorization settings |

Runner means controlled execution, Repository means Git metadata, and WorkingTree
means checked-out state. These objects compose; none authorizes an effect.
Configuration and execution models are distinct from credentials. Credentials and
environment overrides are excluded from ordinary serialization and representations.

## Method vocabulary

| Method | Contract |
| --- | --- |
| `GitCommandRunner.run(command)` | Execute once; return native bytes or a cleanup-aware failure |
| `GitCommandRunner.isolated_home(profile)` | Own a private configuration home for an explicit command sequence |
| `GitCommandRunner.environment(command, home)` | Construct the selected profile without mutating the host environment |
| `GitRepository.run(arguments, ...)` | Execute caller-admitted operations through the shared runner |
| `init_bare`, `fetch`, `object_type`, `is_ancestor`, `changed_paths`, `resolve`, `check_ref_format`, `fsck` | Repository mechanics; caller owns refspec, lease and grant policy |
| `GitWorkingTree.clone_from`, `checkout_detached`, `index_entries`, `status_porcelain`, `sparse_enabled`, `remove_remote`, `remotes` | Working-state mechanics composed with a repository |
| `GitCommand.validate_execution_profile` | Check the read profile and recheck mutable arguments/configuration at execution |

## Environment and credential boundaries

WORKSPACE and HOST_TRANSPORT strip inherited `GIT_*`/`GCM_*` overrides and host
GitHub login variables. Both isolate HOME, USERPROFILE and XDG_CONFIG_HOME and
remove HOMEDRIVE/HOMEPATH. WORKSPACE sets `GIT_OPTIONAL_LOCKS=0` and
`GIT_LFS_SKIP_SMUDGE=1`, and closes stdin with DEVNULL. HOST_TRANSPORT sets
`GIT_ASKPASS=""` and inherits stdin. The runner binds the private credential helper;
normal model-side container Git is never redirected to host execution here.

An explicit sequence can share an isolated home and hooks path. Transport commands
use per-command homes, including the Git 2.31 workaround. Verified publication
selects strict home cleanup; GitHub transport tolerates temporary-home cleanup
errors. Workspace and transport callers supply their 30-second timeouts explicitly.

ISOLATED_HTTPS_READ_ONLY uses a narrow environment, no credentials/hooks/redirects
and HTTPS-only transport. ISOLATED_FILE_READ_ONLY is a trusted constructor test
capability, unavailable through the source HTTP schema. Read profiles reject extra
environment, credentials, protocol/hook overrides and unsupported verbs. Native
cwd is distinct from the `-C` repository argument.

## Budgets, cleanup and errors

Budgeted reads spool stdout and observe output size, a shared monotonic operation
deadline and an optional source-owned cache callback. Expired deadlines are valid
inputs; nonfinite polling values and NaN deadlines are refused. Source cache paths,
labels, registry writes and blob admission stay with Skills.

Source cleanup shares one five-second deadline across process-tree termination,
pipe draining and final wait. Windows launches suspended into an owned Job Object
before resuming, with no breakaway/taskkill fallback; success requires zero active
job processes even after normal root exit. POSIX uses process groups. WORKSPACE
and HOST_TRANSPORT use five seconds per cleanup substep. OS calls add overhead;
these are bounded waits, not hard real-time guarantees.

`GitCommandTimeout` inherits `subprocess.TimeoutExpired` and records
`cleanup_verified`. A timeout never proves an effect did not happen.
`GitCommandLimitExceeded` records a confirmed active-budget refusal;
`GitCommandCleanupError` means termination was not confirmed. Interrupts retain
their original identity/arguments plus the cleanup observation. Uncertain clone
staging must remain available to its potentially active process.

| Caller boundary | Public error translation |
| --- | --- |
| Agent workspace preparation and mediation remote configuration | `git_timeout` or `git_timeout_cleanup_unverified` |
| Skill workspace initialization | `workspace_git_initialization_failed` |
| GitHub push/fetch | Rejection or unknown-effect category and cleanup observation; no automatic retry |
| Verified publication staging | `stage_git_unavailable` |
| Skill source reads | Confirmed limit/access refusal or `repository_cleanup_unverified` |

Startup OSError propagates to the caller's translation. Internal process controls
test these mechanics; live HTTPS, graph and provider acceptance remain distinct.
