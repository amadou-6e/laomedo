# PR249 GitHub: backend review at head `9a741243`

This review covers the backend only. I read all source changes in `backend.diff` (lines 1–2660) and checked them against the head files and their callers. The test changes (lines 2660–7406) I only partly read; details are listed at the end.

## Findings

There are no blocking defects in the backend source.

**G-B-Q1 · question · low · introduced**
- `GitHubOperationIntent` (`src/laomedo/github/models.py:21-43`) now wraps the issue and PR intent hash.
- Any error while building that model is reported as `issue_grant_unavailable` / `pr_grant_unavailable` (`issues/gateway.py:150-165`, `pull_requests/gateway.py:286-301`).
- In practice this path can't be reached: the operation, labels, state, number and the authenticated grant/run strings are all validated before this point.
- Tradeoff: if a future caller passes an operation value that isn't plain JSON, the user would see "grant unavailable" rather than "operation invalid". This is pre-dispatch, so no write happens.

**G-B-Q2 · question · low · pre-existing**
- `experiments/exp19`, `exp100`, `exp104` and `exp139` remain in the production tree. They still import paths this PR retires:
  - `laomedo.github.issues.utils`
  - `transport.git.transport.GitHubMediatedTransport`
- Tests load them only through the import-adapting `load_retained_shared` (`tests/support/retained.py:102-147`, `test_exp19_live_e2e.py:11`). Run directly, they would fail to import.
- This is consistent with keeping their bytes pinned. But "experiments on exp" suggests they should eventually move. Please confirm that keeping them here is deliberate.

**G-B-S1 · suggestion · trivial**
- Wording slips in the READMEs: "Github application interface" (`interface/README.md:1`) and "`GitHubIssue` remain" (`interface/issues/README.md:5`).

## What I verified

- **No behaviour change in the handlers.** `IssueRequestHandler` and the PR handler are exact extractions of the old nested handlers:
  - same bearer comparison, using a token held per server instance;
  - same 1 MiB cap, field sets and routes;
  - same mapping of failures to error codes;
  - a failed write still reports `*_write_unknown` (503) whenever the error is not on the pre-dispatch list.
- **Client unknown-write mapping is unchanged**, as is redirect refusal.
- **Wire records are unchanged.**
  - `GitHubIssue` and `GitHubPullRequest` (strict and frozen) produce the same 9 and 13 fields, and the PR record keeps its historical field order.
  - The new model constraints (`number>0`, `state` open/closed, 40-hex `sha`, and so on) are all already enforced by the manual checks in `issue_value`/`pr_value`. So no new failure path or category appears.
- **Hashes are unchanged.**
  - `issue_digest` is the same function, and `pr_digest` is still the same object.
  - The intent payload has the same six keys and nested `{grant_id, run_id}` binding, with sort-keys canonical JSON.
  - Feedback ticket context keeps the same eight keys.
  - `expected`/digest bindings on reads and writes are unchanged.
- **Transport is unchanged.**
  - `GitHubMediatedTransport` moved verbatim, still checks `repository_mismatch`, and still routes only `git_push`/`git_fetch` to Git.
  - `touches_workflows` matches the old predicate byte for byte, in both the transport and the verified stage.
  - REST transport changes are import-only. The `KnownRejected` codes, the guards that run before any write, the partial/unknown update handling and the no-retry behaviour are intact.
- **Callers are migrated.**
  - The components, viewer routes, host services, the mediation CLI and its validators, and `work_graph` now import from the defining modules.
  - I found no remaining production caller of a retired path in `src/`, `components/` or `docs/`.
  - `validate_repository` keeps its case-preserving behaviour and its error message.
- **No credentials are added to graphs or settings.** Token files are read only by the trusted CLI.

## Verdicts

- **Implementation (backend source): APPROVE.** The three questions/suggestions above are non-blocking.
- **Specification: INCOMPLETE.** I did not read the canonical issue-integration contracts under `specs/projects/laomedo/subsystems/issue-integration`, so I can't confirm conformance to them.
- **Visual: deferred.** No overall UI or PR approval yet; your own inspection and merge authorization remain separate.

## Not read

- The test own-diff bodies (`backend.diff` 2660–7406). I only saw the relocation headers, `retained.py` and the deleted demo test. Shared factories, test grouping and coverage are therefore unverified.
- The canonical specs.
- The archived examples and experiments, and the `archive-preservation.json` bytes.
- `tools/migrations/*.json`.
- `frontend.diff`, `documentation.diff`, the installer and `agents.patch`.
- The control and build logs. Test counts are taken as claims.