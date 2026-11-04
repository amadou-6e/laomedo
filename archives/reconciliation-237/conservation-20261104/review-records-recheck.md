**Both verdicts are APPROVE: RECHECK_UI_CODE APPROVE and RECORD_CONTRACT_TESTS APPROVE.** Your earlier CODE REVISE is closed. Every new record-test expectation matches the exported original data and the original methods; I found nothing that blocks.

## RECHECK_UI_CODE: APPROVE
- **M1 (timeout tests) is fixed.** `records-recheck-shared.diff:10-40` brings back all four test blocks, covering all seven parameter cases. They match `originals/pr-234/.../nodeErrors.test.ts:4-34` character for character: the `model/list` message path, `isKnownNodeError`, the four ACP methods, and the rejection of `https://…`, `session/exec` and `?secret=`.
- **M2 (stray `+` in user-stories) is fixed.** `records-recheck-skills.diff:9-33` removes the literal `+` prefixes. It also states plainly that the paused offline cross-flow placeholder is an inherited constraint and not fresh-history acceptance. It does not claim that case is fixed.
- **The duplicate-key guard now has a single owner.**
  - The Agent copy is removed from `tests/test_shared/test_errors/test_catalogue.py` (`agent.diff:779-792`).
  - The Shared copy is added as `test_catalogue_shape.py` with its own `__init__.py` and README (`shared.diff:41-83`), with the same logic.
  - In the combined tree both files sit side by side under `tests/test_shared/test_errors/`, and nobody else owns that test.
- **The combined popup keeps both behaviours.** Combined `PopupFrame.tsx` still contains the WeakMap stacks, `showPopover`, `stopImmediatePropagation`, the green `#4ADE80` border, `max-height:300px` and the focusable scroll body (8 markers). As before, the separate Shared and Skills branches conflict on adjacent lines, so that merge must be resolved to match this combined file.

## RECORD_CONTRACT_TESTS: APPROVE
I compared assertions and literal values, not just method names.

| New test | Independent source | Result |
|---|---|---|
| `test_store.py` `test_revision_draft_and_frozen_record_match_old_writers` (`shared.diff:101-210`) | `original-skill-records.json` (all three records); pr-220 `test_structured_skill_records.py:15-63` | Hashes, patch text, field and `policy_ref` order, `uuid4` patch, CRLF bytes and extension read are all identical. The forbidden `SkillStoreTests()` instantiation is gone |
| `test_preimages.py` (from the earlier increment) | `original-commit-preimage-records.json` | Both writer IDs and both records match byte for byte. I've now done the cross-check I listed as not done last time |
| `test_intents.py` (`github.diff:18-91`) | pr-220 host records `:142-209` | Same sorted labels, `ensure_ascii=False` preimage, live `grants` binding, model payload and operation key sets. The new `create_case` factories replace the retired cross-test instantiation |
| `test_feedback.py` deadlines (`github.diff:108-161`) | pr-220 `:211-277` | Identical. `expires == 400` holds because the PR factory's clock starts at 100.0 (`test_pull_requests/utils.py:30-31`). `case.provider.writes` replaces `case.fake.writes`, and `patch`/`closing` are already imported (`test_feedback.py:8-9`) |
| Claude `to_claude_record` order (`agent.diff:19-47`) | pr-220 `:110-140` | Identical |
| `test_records.py` with `status-records.json` | `original-agent-records-a9317f6.json` `references` and `join` | All three reference cases, the join case and the `pending_start` default match the original values and order |
| `test_request_records.py` with `request-records.json` | `original-structured-data-a9317f6.json`; pr-219 `:54-62` | Identical |
| `test_preparation_records.py` with `prepared-records.json` | agent records `prepared_*`; pr-219 `:15-41` | Identical. `effective_hash` is recomputed with `_hash_tree` exactly as the original did. `RunnerCase.create()` plus `addCleanup` replaces the `LocalRunnerTests()` instantiation |

## Findings (none blocking)
- **Low:** `test_catalogue_shape.py:81` calls `read_text()` without `encoding="utf-8"`. The catalogue contains one non-ASCII character, so on a Windows non-UTF-8 code page this test could misread the file or fail, depending on locale. The Agent original it replaced had the same omission. Adding `encoding="utf-8"` would fix it.
- **Info, inherited from the originals:**
  - In `prepared-records.json`, the literal `effective_hash` values are overwritten before comparison. They are documented as unchecked.
  - `test_request_records.py` compares the digest and the preimage to their stored literals, but never checks that `sha256(preimage) == digest`. The two literals are consistent in the original data.
- **Uncertainty:**
  - I didn't inspect `RunnerCase.create()` or the issue `create_case` internals beyond their grep hits. I'm relying on your report that these tests pass.
  - I checked the combined tree's files, not its commit ID. I can't confirm the worktree is checked out at exactly c8ccb5f8.

## Read coverage
- **In full:**
  - root `AGENTS.md`;
  - the manifest;
  - all four `records-recheck-*.diff`;
  - `original-skill-records.json`, `original-commit-preimage-records.json`, `original-structured-data-a9317f6.json`;
  - pr-219 `test_structured_agent_records.py`;
  - `test_pull_requests/utils.py` `create_case`.
- **Partially:**
  - `original-agent-records-a9317f6.json` (lines 115–492 in full; lines 1–114 via key grep);
  - pr-220 `test_structured_skill_records.py:1-64`;
  - pr-220 `test_structured_host_records.py:110-279`;
  - grep checks of `test_feedback.py` (imports and `setUp`), issue `utils.py`, the combined `test_errors/` listing, the combined `PopupFrame.tsx` and the catalogue's non-ASCII count.
- **Not checked:** the pr-234 `ErrorPopup` and `SkillHistory` originals, and any logs. I reran no tests.

**VISUAL / real-browser acceptance: PENDING.** No screenshots were submitted in this round. These approvals cover internal code and test fidelity only. They don't approve live, provider or browser behaviour, all-23 conservation, retirement, or any merge.
