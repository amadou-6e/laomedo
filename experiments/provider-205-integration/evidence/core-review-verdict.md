# Develop integration, packet 1 (core.diff): partial review

The parts of `core.diff` I read show no wrong owner, wrong binding or lost control. But I read only about half of the diff, so the core-code verdict is **INCOMPLETE**. The frontend and local-profile/viewer hunks still need reading. No visual approval, and no whole-PR approval.

I didn't re-read `AGENTS.md` this turn; my reading of it earlier in this session applies.

## What I checked

**Runner service (`host/runner/service.py:43-117`, `:182-209`):**
- A shared lease is set by default for every managed provider: `setdefault(lease_service = state/../lease)` and then marked required.
- `image_id` is allowed only for Codex without a Git workspace, and must be an exact sha256 digest.
- The command passes `--lease-service` exactly once; the existing test asserts the count is 1.
- `--image-id` is accepted by `codex/cli.py:27`.
- The CLI module is fixed per provider.

**App launcher (`integrations/langflow/launch/service.py`):**
- It reuses `RunnerService.config()`, so it gets the same normalized config and the lease default. The old rejection for a missing lease is gone.
- It requires a Codex runner and a different port from the runner.
- The token path is derived from the runner state; the token itself isn't read.
- Settings come only from the CLI, and it refuses any path inside Git.
- Health, recovery and starting the runner stay with the shared `RunnerService`, through the viewer's existing recovery action.

**Agent task input (`agents/interface/langflow/component.py:748-770`):** this is the actual owner of the code, and the facade isn't touched.
- `task` now accepts both Message and Data.
- Data that isn't a Message goes through `task_text`, which only accepts a complete, successful PR context. Failed or unknown contexts raise `pr_context_upstream_failed`; anything else raises `pr_context_invalid`.
- Any other type raises `pr_context_invalid` before dispatch.
- Both codes were added to the routable error set.
- Message and plain strings keep the existing behaviour.

**PR component (`components/laomedo/github_pr.py`):**
- It now has one input (`pr_context`) and one output (`pr`).
- An incoming context must match the repository and any explicit picker selection.
- Only a typed `PRContextOperation` becomes an operation, and the content digest is passed as `expected`.
- The feedback seed uses `task_text(initial)`.

**PR feedback loop (`feedback/pr.py`):**
- Port names change only for `LaomedoGitHubPR`; Skill feedback keeps its `task` port.
- An agent output going anywhere other than the PR controller's `pr_context` is refused.

**Codex agent component:** the default runner URL now comes from `Settings().codex_runner_url`.

**Agent, Docker and Activity files:** the changes there only flatten imports into one import per line. Every new owner path I saw is consistent:
- `host.http.NoRedirect`;
- `skills.registry.utils.files` and `skills.registry.utils.hashing`;
- `skills.operations.utils.proposal.proposal`.

I saw no `TYPE_CHECKING` block moved to runtime, no alias collision, and no change to the bound semantics of any function.

## Questions (not confirmed defects)

**Q1: `feedback/pr.py:190` calls `component.graph._replace_conditional_exclusions`.**
- Nothing in this repository defines it, so it must be a private method of the pinned lfx 1.12.3 Graph.
- This code comes from develop. Please confirm the method exists in the installed runtime and is covered by a test. If it's missing, a PR feedback round trip raises `AttributeError`.

**Q2: `feedback/pr.py:222-227`, in `agent_operation`.** `starts` is now empty whenever `feedback` is `None`. I couldn't see the condition that follows (`:2974`), so I haven't verified whether a non-feedback call still behaves the same as before.

**Q3: `component.py:721-722`.** A raw dict task that has no PR keys and isn't Data goes to `Message(**dict)`. A malformed dict would then raise a pydantic error rather than the routable `pr_context_invalid`. This edge case only applies to an unusual API tweak.

## Not read, so not covered by this verdict

- **Frontend:** `core.diff:261-2180`:
  - RecoveryPopup and RunnerRecovery;
  - the agent input controls;
  - PRNodeControls and PRSelectors;
  - the node error catalog;
  - every `profiles/*` file.
- **Local profiles, viewer and tools:** `core.diff:3188-4200`:
  - `local_profiles/*` (admission, auth, boundary, registry, routes, runtime);
  - `langflow/settings.py`;
  - `skill_editing.py`;
  - `viewer.py`;
  - `tools/apply_langflow_*.py`.
- I did not open the tests you named for the PR task path (`test_github`, `test_pull_requests`, `test_graph/test_agent_input.py`).
- `imports.diff`, `tests.diff` and `docs.diff` are separate packets and unread.

## Checks and visual limits

- The full test run (`tests-second.log`) has not finished, so I'm not claiming a pass.
- The frontend build is still running. Your report of 33 frontend tests passing comes from `frontend-tests-fourth.log`, which I didn't open.
- There's no visual approval for the combined artifact. Still needed:
  - Skill default and Advanced views;
  - connected Prior Run;
  - the new single-port PR node;
  - the profile entry and recovery popups.

## Broader integration checks still needed

- the unread hunks above;
- a real-graph run of the PR → Agent → PR feedback loop on the pinned runtime, which covers Q1 and Q2;
- the native app launch through `AppLauncher` starting a supervised Codex runner;
- the full suite completing at this head.

## Verdict

**Core code: INCOMPLETE.** There are no confirmed defects in the roughly 1,260 lines I read (`core.diff:1-260` and `:2181-3190`); the questions above are still open. Nothing about the unread parts is approved.