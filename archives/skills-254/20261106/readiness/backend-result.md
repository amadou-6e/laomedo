# PR254 Skills, Packet 1 review: backend, installer, tests and standalone deployability

**Scope:** `skills-followup-206`, base `37dc9aa9`, head `97268834`. I read the whole backend own-diff (`backend.diff` 1–3315, including earlier commits) and checked it against the head source. The inventory's frontend and docs entries were checked only where the backend depends on them.

**Isolation answer:** I found no missing prerequisite. Skills on develop does not structurally need Shared255, GitHub249 or Agent250. It has not been shown to run in isolation, though: every test and browser result comes from the four-PR combined candidate.

## Isolation trace

- **Backend imports.** `skill.py:19` uses `laomedo.agents.feedback.pr`. `viewer.py` uses `laomedo.activity.agent_activity.routes` and `laomedo.host.runner.routes`. All three are develop paths and exist at head.
- **Persistence.** Everything stays inside Skills: the registry, the journal, and the new `manual_saves`/`manual_publications` tables.
- **Installer.** It only uses overlay files that ship in this PR, plus the `laomedoErrors` set that develop's installer already copies.
- **Error catalogue.** The develop location `node-error-catalog.json` contains all 10 `MANUAL_ERROR_CODES`.
- **The only Shared255-aware code** is a test helper (S1).

## Findings, most severe first

No defect is proven. Where a severe concern isn't proven, it is listed as a question.

**PR254-B-Q1 · question · medium · introduced** — `service.py:105-131,145-148`
- **Trigger:** a registry was promoted with no journal (a pre-PR deployment). A saved graph is pinned to the promoted latest with an empty Base Commit, and an Operation arrives.
- **Mechanism:**
  - `_import_head` records the root and then every later revision in the lineage, so the head is no longer the root.
  - `prepare` with an empty `commit_id` requires `parent_commit is None`, so it raises `skill_base_changed`.
  - Previously, the first prepare created the root at the current revision.
- **Evidence:** this is intended. `test_import_history.py` (diff 2472-2473) asserts it, and the operations README (diff 533-534) documents it.
- **Consequence:** saved Operation graphs that used to work now fail until someone pastes the head commit into Base Commit, which is now under Advanced.
- **Question:** does the `skill_base_changed` recovery text tell the user where to find that commit? If not, should the backfill accept an empty Base Commit when it is the first edit after backfill?

**PR254-B-Q2 · question · medium · introduced** — `manual.py:122-163,206-212`; `service.py:107-109`
- **Trigger:** canonical latest moves through a promotion this journal didn't record. Examples: a second operations server on the same registry, or a direct `store.promote_draft` call as shown in `docs/features/skills/registry.md:36`.
- **Mechanism, part 1 (silent revert):**
  - Once a journal head exists, it never picks up later promotions.
  - The frontend sends `expected_latest = state.latest_revision`, read fresh (`SkillEditing.tsx:135`).
  - `_publication_draft` only checks that latest equals `expected_latest`. It does not check that the candidate descends from that latest. It then writes the candidate tree over it.
  - Result: the other promotion's changes are reverted. The publish summary only shows "N files to publish" (`SkillFilesModal.tsx:203`).
- **Mechanism, part 2 (no recovery):** `editor()` on the new latest always returns `can_edit=false`, and `prepare` on it raises `skill_base_changed`. Nothing records that revision afterwards.
- **Evidence:** read from the code. `test_manual.py` (diff 2705-2731) only covers a stale `expected_latest` value, not refreshed state.
- **Uncertainty:** whether out-of-journal promotion is a supported deployment. The operations README says ordinary operations never promote. If it is not supported, say so explicitly. If it is, add an ancestry check and refuse with `skill_manual_stale`.

**PR254-B-Q3 · question · low-medium · newly exposed** — `store.py:192-202`, `store.py:397`, `handler.py:83`
- **Trigger:** a crash during legacy backfill or during promotion.
- **Mechanism:**
  - A stale `import.lock` raises `import_busy`. `history()` and `prepare()` now reach this on the **read path**, and it maps to `unavailable`.
  - A stale `promotion.lock` raises `promotion_busy`, which maps to `skill_manual_stale`. The frontend treats that as final (`SkillEditing.tsx:107-109`), so it refreshes and fails again every time.
- **Consequence:** history, editing or publishing stay blocked until someone deletes the lock by hand. The "stale" message points the user to the wrong cause.
- **Origin:** the lock pattern already existed on develop. Reaching it from read paths and the stale mapping are new.

**PR254-B-Q4 · question · low · introduced (spec)** — `skill.py:76-82,137-164,185-208`
- The legacy feedback path still exists: a hidden `edit_request` is read from `vertex.full_data`, and the Agent prompt still says "Edit request".
- New graphs with a feedback edge fail with `skill_feedback_request_required`. `test_graph.py` (diff 2312-2324) asserts this.
- **Question:** is keeping the hidden field for saved graphs the intended reading of "remove Edit Request" and "no retired facades"?

**PR254-B-Q5 · question · low · introduced** — `models.py:343-364`
- `from_registered_revision` uses `now()` and a `uuid4` nonce. If the journal is recreated, the registered commit IDs change, unlike the stable IDs from `from_import`.
- Any Base Commit saved for a registered head would then fail with `skill_base_changed`.
- Is journal recreation in scope?

**PR254-B-S1 · suggestion · low · introduced** — `tests/support/paths.py:error_catalogue_path` (diff 1636-1653)
- This helper finds the catalogue in either the flat layout or Shared255's `errors/` layout. That anticipates an unmerged PR from inside a PR meant to stand alone.
- `test_errors.py` (diff 2104-2107) hard-codes the flat path, so the two are inconsistent.
- **Suggestion:** use only the develop layout and let Shared255 own the move.

**PR254-B-S2 · suggestion · low · introduced (scope)** — `tests/test_container_lease.py` (diff 1654-1696)
- These are host-lease timing changes plus a new `late_owned` test, inside a Skills PR. They pass against develop's `cleanup_after_loss` (`host/leases/utils.py:116-135`), so they are harmless.
- **Suggestion:** move them to a host PR.

**PR254-B-S3 · suggestion · low**
- **Orphan drafts:** if `_publication_draft` fails after `create_draft` or `freeze_draft` (`manual.py:140-162`), the draft is left behind. `apply` already had this pattern.
- **Misleading code:** a made-up `commit_id` in publish produces `skill_commit_unavailable`, which maps to `unavailable`. The frontend then keeps the request pending, and Reconcile resends the same doomed request. Mapping it to `invalid` would end that loop.

## What checks out

- **Publish idempotency:** works through the promotion log and `_published`, including after a lost reply or a revoked grant (diff 2733-2808).
- **Rechecks before promoting:** the policy hash and head are checked again inside `BEGIN IMMEDIATE`, then `promote_draft` does a base compare-and-swap.
- **Save replay and conflicts:**
  - replaying a save is safe;
  - concurrent saves with the same UUID converge on one ticket;
  - a save with the same UUID but different content raises a conflict.
- **Expired saves:** a retry gets `save_expired`, which the frontend treats as final, so the next attempt gets a new UUID (`SkillEditing.tsx:137`).
- **Concurrent first reads:** they don't create duplicate import roots (diff 2393-2411).
- **Binary admission:** canonical base64, the 512 KiB cap, copy-from-before only, and all-or-nothing refusal.
- **Langflow route:** authentication, the Origin check, an action allowlist, a 4 MiB cap, and non-leaking errors.
- **Corrections, backend side:**
  - Revision is under Advanced (`skill.py:50`).
  - The exact failure text "Discovery failed. Check source access and refresh." (`skill.py:401-403`) matches `SkillNodeControls.ts:21-25`.
  - "No source found" comes from `SkillNodeControls.ts:27-32`. That belongs to the frontend packet, so I only cross-checked it.

## Verdicts

- **Implementation: INCOMPLETE.** No defect is proven. Q2 and Q3 involve persistence and recovery and are unresolved. There is no isolated test run.
- **Specification: INCOMPLETE.** The owner needs to decide Q1, Q2 and Q4. S1 and S2 touch the user's isolation and concern-ownership requirements. The frontend and docs packets are still pending.
- **Visual:** deferred.
- **User validation and merge:** not inferred. They remain separate gates.

## Evidence and coverage gaps

- The 1014 Python / 811 frontend test pass and the browser stories all ran on the combined candidate. There is no isolated develop+PR254 test run, installer run or browser run.
- `canvas_refresh.cjs`, `files.cjs` and `sources.cjs` describe themselves as supporting regressions or fixture checks, not acceptance runs.
- `test_manual_routes.py` skips when FastAPI is absent (diff 2904-2907).
- No test covers out-of-journal promotion followed by a refreshed publish (Q2).
- No test covers stale lock files (Q3).
- No test covers journal recreation with registered revisions (Q5).
- **Not read in this packet:**
  - the frontend overlay beyond the files cited here;
  - the integration patches (`upstream.patch`, `file-actions-dependencies.patch`);
  - docs and assets, and the examples, including the deleted ones and the moved `examples/graph.py`;
  - `CURRENT-HANDOFF.md` in full;
  - develop's `service.py` before this PR — I took the earlier `prepare` behaviour in Q1 from the diff;
  - `models.py` beyond the cited ranges.

## Recheck targets

1. An isolated develop+PR254 test run, installer run, and one real manual save-and-publish in the browser.
2. Q2: an ancestry check, or an explicit statement that only one journal is supported.
3. Q3: recovery from stale locks, and the `promotion_busy` mapping.
4. Q1: the recovery text for `skill_base_changed`.
5. S1 and S2: scope cleanup.