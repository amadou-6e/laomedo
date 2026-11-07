# PR249 final packet at head `f7b233be`: G-F-D1 recheck and the remaining test comparisons

G-F-D1 is resolved. The remaining moved test bodies match their deleted originals, with no lost or weakened safety assertions. I did not read `documentation.diff`, so I can't give full-PR approval; the live and integration gaps listed at the end also remain open.

## G-F-D1 recheck: resolved

- **Catalogue restored:** `catalogue-fix.diff` puts the `unauthorized` and `invalid_request` entries back exactly as they were on develop `7c72d94`. That includes the runner wording and the "until any existing execution is accounted for" recovery advice. The shared runner/Agent message copy no longer differs from base.
- **Viewer handling:** `InspectionError.tsx:10` now also sends `unauthorized` and `invalid_request` to the viewer's own read-only fallback message.
  - That message says only "repeats only this read… does not edit GitHub, run the graph or start an Agent".
  - The diagnostics keep the original safe code, because they come from `failure.diagnostics`.
  - The path is the inspect (read) request, which carries no `operation` field, so this cannot suggest retrying a write.
- **Test:** the new test (`InspectionError.test.tsx:62-72`) checks the fallback title and the read-only recovery for both codes, checks the code is kept, and checks the text has no "runner" wording. I did not re-run the 407 tests; that count is your evidence.
- **Scope:** no change to operation codes, runner code or the wire schema.

## Other earlier findings

- **G-F-Q1 (tests deployed with the frontend):** closed as intentional. Excluding them would only be an optional convention change.
- **G-V-Q1 (✓ on the error card):** closed. It is the 2-second "copied" state from the capture script clicking Copy. I did not read `CopyIcon.tsx`, so this relies on your description; the new idle screenshot will confirm it.
- **G-V-S1 (modal layout):** stays an optional suggestion for existing layout.
- **G-T-Q1 (factories skip model validation):** stays a non-blocking question.

## Test comparisons completed

- **PR gateway** (`test_pull_requests/test_gateway.py:5437-5598` against the deleted `test_live_github_pr.py:6862-7128`):
  - All 12 test bodies match line for line; only `self.fake` and similar became `self.case.*`.
  - That includes `test_fork_merged_changed_branch_and_changed_head_refused` (foreign fork, merged, changed head branch, all with zero writes) and `test_partial_metadata_labels_operation_stays_unknown` (labels rejected after the title write: unknown, replayed, exactly 1 write).
  - The provider double (`provider.py:5145-5201`) and `raw_pr` match the deleted `FakeGitHub` and `raw_pr`. The only change is the shared response helper (`test_github/response.py`).
  - `create_case` issues the same grant: `target_prs={1:"main"}`, branch `demo`, ttl 60, clock starting at 100.
- **Interface tests:**
  - The issue HTTP tests (`test_interface/test_issues/test_http.py`) are identical to the deleted ones: loopback 401 and redaction, uncertain client delivery (timeout, reset, 503 and a bad body all become `issue_write_unknown`, while a 400 grant refusal stays a refusal), and an unexpected server error returning 503 `issue_write_unknown`.
  - `test_pull_requests/test_http.py` changes only its import.
  - Three new files add checks:
    - `test_admission`: bad tokens and non-loopback hosts are refused before any socket is opened;
    - `test_bindings`: each server instance only accepts its own token, and responses are `no-store`;
    - `test_client`: Issue-only codes such as `github_http_403` are not passed through as PR codes.
  - `test_presenters` checks catalogue coverage for the viewer's error codes, the installer's `copytree`, and the import paths in the patch files.
  - `test_reviewed_cli` only changes how it finds the adapter (URI via `MEDIATION_CLIENT`); the GraphQL equality check and the request assertions are kept.
- **PR graph tests (`test_graph/*`):**
  - `test_component.py` replaces the borrowed setup with `create_case`; its assertions are unchanged.
  - `test_feedback.py` (the Agent loop) changes only paths and helpers: the builder, operation and result now come from test-owned files, and patch targets moved to `interface.pull_requests.client`.
    - Unchanged checks: a normal acyclic operation (1 write, 0 Agent calls), external Agent input and multiple operation sources refused before the Agent runs, and a downstream inspector with a single Agent run.
  - `test_inspection.py` changes only patch targets.
  - The fixture `agent.py` and `builder.py` are clearly labelled as fixtures.
- **Issue graph tests (`test_issues/test_graph`):** `test_component` and `test_inspection` change only imports and patch targets.
- **`test_ownership.py` (204 lines, read in full):**
  - migration rewrites are compilable and idempotent; star or unknown names and `getattr` access require manual migration;
  - retired modules are gone and map to their new owners;
  - the GitHub core imports no lfx or work_graph modules;
  - one definition kind per file;
  - the mediated dispatcher passes the exact payload and binding through and re-raises the same uncertain exception;
  - each CLI owns its own `main`;
  - no test imports `experiments` or `support.retained`.

## Findings

**G-T-S2 · suggestion · low · introduced**
- Where: `test_pull_requests/test_graph/test_feedback.py:6025-6027`.
- The old test loaded the saved `examples/github-pr/flow.json`. The new one rebuilds the flow from the test builder and round-trips it through JSON.
- That fits archiving the saved file. But the test no longer protects a saved export, and the new `builder.py` was not compared with the archived `build_flow.py` (that file's deletion is outside these hunks).
- Not a safety regression, because the feedback-edge and graph checks still run on the generated flow.

No defects found in this packet.

## Verdicts

- **Frontend implementation: APPROVE** for the files I read, at `f7b233be`; G-F-D1 is resolved.
- **Tests: APPROVE** for every substantive moved or new body listed above. No lost authorization, no-retry, identity or outcome assertion. These are internal fixture checks, not proof that the live system works.
- **Spec:** the earlier APPROVE stands (merged as specs PR409 `125137a`).
- **Visual:** limited to the four earlier images and your PASS report in `real-recovery.json`. I did not open `real-recovery.json` itself, or any final-build or idle screenshot. This is not full UI approval.
- **Whole PR: not approved.** `documentation.diff` is unread, and the items below are unverified.

## Not read or not verified

- **Not read:**
  - `documentation.diff` (the architecture, link and consolidation docs and their claims about methods and ownership);
  - `CopyIcon.tsx`, `ErrorExplanation`, `examples/graph.py`, `components/laomedo/github_{issue,pr}.py`;
  - the unchanged middle of the renamed graph test files beyond the hunks shown;
  - browser `.cjs` and `prepare`/`serve` scripts (renames);
  - `test_context/*`, `test_values` and `test_errors` beyond packet 2;
  - `tests/support/*`, `test_shared/test_migration/test_imports.py`;
  - the `archive-preservation.json` contents and the exp archive.
- **Bodies not compared:** zero-line transport and mediation renames, and the old `examples/github-pr/build_flow.py` against the new test `builder.py`.
- **Evidence not read or checked:** `real-recovery.json`, `catalogue-fix-jest.json`, the final frontend build, the new idle and recovery screenshots.
- **Not verified:**
  - real mutation and uncertain-delivery acceptance;
  - the current standalone wheel and the full TypeScript check against baseline;
  - your final workflow validation.