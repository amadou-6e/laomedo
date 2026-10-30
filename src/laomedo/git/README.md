# Shared Git mechanics

One owner for reusable host Git mechanics: `GitCommandRunner`, `GitRepository`
and `GitWorkingTree`. The standard-library-only credential helper remains under
`credentials/helper.py`. Agent admission, selected GitHub connections and
publication decisions stay with their feature owners.

## Reviewed replacement contract

The implementation uses one `GitCommandRunner.run(GitCommand)` implementation,
with canonical Pydantic `GitCommand`, `GitExecutionContext` and `GitCredential`
values in `models.py`. Context groups profile, timeout, temporary home and source
hardening. Credentials and environment overrides are excluded from ordinary dumps
and representations. The runner alone builds the existing private helper binding.

`GitEnvironmentProfile.WORKSPACE` and `HOST_TRANSPORT` preserve the existing
environment builders exactly: both strip inherited `GIT_*`/`GCM_*` overrides and
host GitHub login variables. WORKSPACE sets `GIT_OPTIONAL_LOCKS=0` and
`GIT_LFS_SKIP_SMUDGE=1`; HOST_TRANSPORT sets `GIT_ASKPASS=""`. Both isolate HOME,
USERPROFILE and XDG_CONFIG_HOME and remove HOMEDRIVE/HOMEPATH. A sequence can
share `GitCommandRunner.isolated_home()` so its hooks path stays stable; ordinary
transport commands retain per-command homes, including the Git 2.31 workaround.
Verified publication retains its original stricter home-cleanup behavior through
the context's explicit cleanup policy; the GitHub transport still ignores those
cleanup errors as before. These two earlier profiles retain their existing behavior; the separately described D2 profiles do not broaden them.

Stdin behavior is deliberately preserved: WORKSPACE closes stdin with DEVNULL;
HOST_TRANSPORT retains inherited stdin. There is no speculative stdin setting.
The review suggested closing both; this refactor preserves existing behavior.
Both current caller timeouts are 30 seconds; cleanup uses the existing five-second
bound. Callers still supply their timeout explicitly rather than changing policy
through a new deployment setting.

| Object / methods | Contract and effects |
| --- | --- |
| `GitCommandRunner.run(command)` | Execute one admitted command with its profile, bounded process group and exact cleanup accounting; never authorize an effect. |
| `GitCommandRunner.isolated_home(profile)` | Own one private temporary configuration home for an explicit sequence. |
| `GitRepository.run(arguments, ...)` | Low-level trusted operations that have caller-specific refspec/lease policy; one bounded execution path. |
| `init_bare`, `fetch`, `object_type`, `is_ancestor`, `changed_paths`, `resolve`, `check_ref_format`, `fsck` | Shared object-database mechanics with existing safety flags; no remote URL or grant selection. |
| `GitWorkingTree.clone_from`, `checkout_detached`, `index_entries`, `status_porcelain`, `sparse_enabled`, `remove_remote`, `remotes` | Checked-out working state mechanics composed with a repository; no Agent admission or publication decision. |

`GitCommandTimeout` retains `subprocess.TimeoutExpired` inheritance and the
`cleanup_verified` observation. A timeout never proves the effect did not happen.

| Boundary | Preserved translation |
| --- | --- |
| Agent workspace preparation | `GitWorkspaceError("git_timeout")` or `git_timeout_cleanup_unverified` |
| Skill baseline initialization | `WorkspaceSkillError("workspace_git_initialization_failed")` |
| Mediation remote configuration | Existing `GitWorkspaceError` timeout categories, exported through the public Agent error boundary |
| GitHub push/fetch | Existing rejection/unknown-effect categories and cleanup observation; no automatic retry |
| Verified publication staging | `VerifiedGitStageError("stage_git_unavailable")` |

OSError from process startup still propagates to these boundaries. Workspace
admission, selected connection, repository/ref authorization, workflow-path policy,
immutable bundle verification and publication status remain with their callers.
The stronger existing transport cleanup algorithm replaces both process runners.
Real host registrations use the default runner; test injection accepts an explicit
runner object rather than retaining a parallel legacy subprocess implementation.

| Object nomenclature | Responsibility / method vocabulary |
| --- | --- |
| `GitCommandRunner` | Controlled command execution, deadlines and process-tree cleanup; `run` returns a process result or explicit timeout uncertainty. |
| `GitRepository` | Repository mechanics: inspect, clone, fetch and remote operations as actually needed by callers. |
| `GitWorkingTree` | Checked-out file state: checkout, status and commit operations as actually supported. |

No caller authorization moves here: Agent admission stays in workspaces, GitHub
request/push policy in its transport, grants/credentials in trusted host services.
Never route normal model-side container Git to host execution through these objects.
Centralization must replace both existing process runners, with caller-specific
stable error translation and exact cleanup behavior preserved.


## D2 source-read extension contract

This design is recorded before implementation. The shared runner gains active
spooled-output/deadline/budget observation through a canonical
`GitExecutionBudget` in `models.py`; it does not learn Skill cache paths, labels,
registry writes or source admission. An optional source-owned budget callback is
excluded from representation/serialization. `GitTreeEntry` groups native mode,
kind and object identity without granting access or changing source blob policy.
Existing GitCommand/Context/Credential models remain canonical.

`ISOLATED_HTTPS_READ_ONLY` preserves the source launcher's narrow environment and
ordered no-credentials/no-hooks/no-redirect/HTTPS-only configuration. A distinct
`ISOLATED_FILE_READ_ONLY` profile is selected only by the existing trusted
constructor test adapter; the production profile rejects attempts to smuggle
file transport, credentials, hook/protocol configuration or extra environment.
Native command cwd is separate from the existing `-C` repository argument.
Only the read/cache Git verbs used by this boundary and the version query are
admitted; selecting a profile never grants a GitHub effect.

The runner owns Popen, process groups, polling, spooled stdout and bounded tree
cleanup; there is no second source launcher. Source-owned cache budget checks
are invoked at the same polling point. `GitCommandLimitExceeded` records the
active budget refusal and cleanup observation without exporting native output.
`GitCommandCleanupError` means termination was not confirmed; callers must not
report successful cleanup or infer a safe retry. Source translation preserves
confirmed-cleanup categories and introduces the explicit
`repository_cleanup_unverified` category only for that uncertainty case.

Budgeted source reads share one five-second cleanup deadline across native tree
termination, pipe draining and final wait. Legacy profiles keep their existing
five-second bound per cleanup substep. Process creation, polling and native kill
calls add operating-system overhead; neither rule is a hard real-time guarantee.
The source operation retains its 60-second deadline and existing 65-second HTTP
client timeout, so an HTTP timeout can still win that race and retain the safe
transport fallback rather than deliver a cleanup category.

| D2 object / methods | Contract |
| --- | --- |
| `GitExecutionBudget` | Group stdout cap, shared monotonic operation deadline, finite polling interval and excluded caller accounting callback. An expired deadline is admitted; NaN is refused. |
| `GitCommand.validate_execution_profile` | Validate trusted read-profile construction and recheck mutable argument/configuration containers at execution; never grant caller authorization. |
| `GitCommandRunner._execute_budgeted` | Reuse the single native launcher, spool stdout and inspect active output, operation time and caller budgets. |
| `GitCommandRunner._stop_tree`, `_cleanup_timeout` | Apply the selected cleanup budget and retain uncertainty on native failure; no success inferred from an exited root alone. |
| `GitTreeEntry` | Carry native mode, object kind and object identity; path/blob admission belongs to the source consumer. |

Legacy WORKSPACE/HOST_TRANSPORT environment, argv, stdin, credential helper and
completed-result behavior remain unchanged. Their existing timeout categories
and cleanup fields are preserved. The new bounded-source controls compare against
an independent old-launcher capture and exercise real controlled processes,
including descendants; they do not establish live HTTPS or provider acceptance.
