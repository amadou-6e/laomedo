# nonpython-frontend: COMPLETE (dispositions); two items UNVERIFIED

I read the whole packet: the index and `.txt` lines 1-300, 301-600, 601-900, 901-1200, 1201-1500, 1501-1800, 1801-2100 and 2101-2290. Nothing in the packet is unread.

Two items stay **UNVERIFIED**:
- **Final combined head:** I have no read path for `1eb10a1f`. The closest tree I could read is c8ccb5f8 at `.tools/reconciliation-integration-237`.
- **Browser and visual behaviour:** nothing was run and no screenshots were supplied.

All 23 PRs remain **HOLD**. Provider, browser, visual and owner gates are separate.

**These changes are split across three of the frozen heads, not one owner:**
- **Shared255:** the shared presenter (`nodeErrors.ts`, `PopupFrame.tsx`) and most new catalogue keys.
- **Skills254:** the viewer components, `upstream.patch`, the installer and the viewer README.
- **Agent250:** the Agent-specific rewording of catalogue entries.

None of the three trees is consistent on its own (frontend-Q1). On the frozen evidence, GitHub249 does not carry these frontend changes: its `nodeErrors.ts` lacks the timeout and credential filters, and I checked nothing else there.

## Disposition by entry

| # | PR / path | Disposition | Current evidence |
|---|---|---|---|
| 1 | 213 `PopupFrame.tsx` | **PRESERVED** in Shared255 | The short-screen padding, scrollable `role="group"` body and `recovered` prop are present in Shared255's `PopupFrame.tsx` (6 grep matches). Agent250 and Skills254 carry the pre-213 version (Q1). |
| 2 | 213 catalogue | New keys **PRESERVED**; operator rewordings mostly a **GAP** | All 47 keys I sampled across PRs 213-234 are present in Shared255's catalogue. Four of the five PR 213 "operator" rewordings are missing (D2). |
| 3, 4 | 213 `nodeErrors.test.ts` / `.ts` (native timeout) | **PRESERVED** in Shared255 | `nodeErrors.ts:13-14,28`; tests at `nodeErrors.test.ts:190-205`. |
| 5, 6 | 214 `RecoveryPopup(.test).tsx` (exact blobs) | **PRESERVED** | The `recovered` prop it uses exists (`PopupFrame.tsx:15` in Agent250 and Shared255). The installer copies both files into the recovery folder. |
| 7 | 214 catalogue (`turn_timeout`, `cancel_native_unconfirmed`, `executor_lost`, …) | **PRESERVED** | Agent250 catalogue lines 1487-1760; also in Shared255. |
| 8, 9 | 214 `nodeErrors` ACP `session/*` timeouts | **PRESERVED** in Shared255 | `nodeErrors.ts:13`; tests `:206-221`. Agent250 produces these codes (`base/acp/session.py:282`, routed at `interface/langflow/component.py:174-186`) → Q1. |
| 10 | 216 catalogue | **PRESERVED** | The `opencode_model_discovery_in_progress` rewording is in Agent250 (`:1275`) and asserted by `test_catalogue.py:137`. Producers for the Git and working-state keys are covered at `test_catalogue.py:143-186`. |
| 11 | 220 `invalid_join_body` | **PRESERVED** | Agent250 `test_catalogue.py:107-112`. |
| 12, 13, 17, 20 | 222 source/GitHub keys, 223 `bundle_*`, 226 registry keys, 228 `repository_cleanup_unverified` | **PRESERVED** (the entries) | Present in Shared255's catalogue. T4-D4 (catalogue coverage for registry errors) carries forward. |
| 14, 15 | 224 README and `SOURCE-DEPLOYMENT.md` (`skills.interface.sources.cli`) | **PRESERVED** | Skills254 `README.md:198` and `SOURCE-DEPLOYMENT.md:9`. |
| 16 | 225 catalogue (Claude discovery and login-copy recovery) | **GAP** | D3 |
| 18 | 227 README paragraph | **INTENTIONALLY_SUPERSEDED** (it was provenance) | The remaining "operator" wording follow-up is S2. |
| 19 | 227 `lease_service_*` / OpenCode rewording | **PRESERVED** in Agent250 | Lines 422 and 1247, and c8 `:417`. Shared255 still has the old text (`:417-420`) → Q1. |
| 21 | 234 `CanvasQueryState.test.ts` (exact) | **PRESERVED** | The Skills254 installer copies it to `PageComponent/__tests__` (`apply_langflow_skill_viewer.py:161-163`). |
| 22, 24 | 234 `ErrorExplanation.tsx`, `ErrorPopup.tsx` (exact) | **PRESERVED** | `ErrorPopup.tsx:2,14,17` imports them; the installer's error list includes them. The missing installer-name check stays in T5-S3. |
| 23 | 234 `ErrorPopup.test.tsx` (credential-shaped node IDs) | **PRESERVED** in c8 | `ErrorPopup.test.tsx:30-33` (seen in tests-5). I didn't re-locate it in a frozen head. |
| 25 | 234 README (keyboard boundary, canvas lifetime, inspection-failure table) | **PARTIAL** | Condensed to Skills254 `README.md:244-250`. The revision-specific provenance was rightly dropped (S1). |
| 26, 27 | 234 `SkillFilesModal(.test).tsx` | **PRESERVED** in Skills254 | **Keyboard isolation:** `SkillFilesModal.tsx:52,68`.<br>**Failure presentation:** `:116,128`.<br>**Tests:** `SkillFilesModal.test.tsx:45,55,66,83`. |
| 28, 29 | 234 `SkillHistory(.test).tsx` | **PRESERVED** in Skills254 | `SkillHistory.tsx:5,33,79` (the history and comparison fallbacks). The catalogue entries they need are absent from Skills254 → Q1. |
| 30, 31 | 234 `SkillInspectionError(.test).tsx` (exact) | **PRESERVED** | **Installer:** `:226-230`.<br>**Used by:** `SkillFilesModal.tsx:32` and `SkillHistory.tsx:5`. |
| 32 | 234 catalogue (inspection entries) | Entries **PRESERVED** in Shared255; `invalid_skill_id` rewording a **GAP** | Shared255 `:1447,2182-2207`. For `invalid_skill_id` see D2. |
| 33, 34 | 234 `nodeErrors` credential-prefix filter | **PRESERVED** in Shared255 | `nodeErrors.ts:15,29,98`; tests `:167-188`. |
| 35 | 234 `upstream.patch` (exact) | **PRESERVED** | Skills254 `upstream.patch:374-381`; the installer applies it (`:27`). |
| 36 | 234 `tests/browser/canvas_refresh.cjs` | **GAP** | D4 |
| 37 | 234 `tests/browser/skill_files.cjs` | Moved to `tests/test_skills/test_browser/files.cjs`, but with pre-234 content → **GAP** | `test_layout.py:26` asserts the old path is gone. See D1. |

## Findings

**frontend-D1 — defect, medium. Owner: Skills254.**
- **What's wrong:** `tests/test_skills/test_browser/files.cjs:52-60` still contains the pre-234 harness. It expects:
  - the raw code `skill_revision_unavailable` in the alert;
  - a `Retry` button after an immutable refusal.
- **Why it fails:** current `SkillInspectionError.tsx` shows a title and offers no reload for refusals. So the harness would break at line 60 against the current UI.
- **What PR 234 asserted and is now lost:**
  - no futile reload after a refusal;
  - for an unknown failure, `Reload files` repeats only the same read;
  - `private-body` never appears.
- **Not run:** I did not execute the browser harness.

**frontend-D2 — defect, medium. Owners: Agent250 and Skills254.**
- **PR 213:** it removed "Ask the operator" from five cleanup and isolation codes. Only `container_termination_unverified` was updated (Agent250 `:462-465`). These four still say "Ask the operator…" in Agent250, Shared255 and c8 (`:457-480`):
  - `protected_mount_changed`
  - `executor_termination_unverified`
  - `run_preparation_cleanup_unverified`
  - `opencode_transport_cleanup_failed`
- **PR 234:** its viewer-specific recovery for `invalid_skill_id` was reverted to "…or disconnect the optional Skill Reference" in all heads (`:767-770`). `SkillFilesModal.tsx:116` emits that code inside the viewer, where no such control exists.
- **Rule broken:** `AGENTS.md` requires recovery text that matches the actual UI and doesn't invent an operator.

**frontend-D3 — defect, medium. Owner: Agent250. Linked to T2-D4.**
- **What was lost:** PR 225's recovery wording for two codes. Every head still has the old text.
  - `runner_model_catalog_unavailable_check_runner_connection` (`:182-185`) no longer warns that a timed-out Claude discovery may still be running, or says to avoid repeated Refresh or restarting a healthy runner.
  - `claude_local_login_copy_failed` (`:1087-1090`) lost its guidance on:
    - directory ownership;
    - copies still in progress;
    - not deleting a pending receipt.
- **Why it matters:** the login-copy mechanism with its deadlines still exists (`claude/auth/utils.py`), so the protection against unsafe repeat advice is gone.

**frontend-D4 — defect, low. Owner: Skills254.**
- **What was lost:** `canvas_refresh.cjs`, the browser regression that holds a builds response in transit and checks the viewer stays mounted. It is absent from Skills254 `tests/**/*.cjs`, and the README no longer mentions it.
- **What remains:** `CanvasQueryState.test.ts` covers the query flags but not the mounted child.
- **Severity:** PR 234 itself labelled this harness supporting-only.

**frontend-Q1 — question, high. Owners: integration / merge order.**
- **The problem:** the frozen heads are not consistent on their own.
- **Agent250:**
  - It raises `request_timeout:<method>`.
  - Its `nodeErrors.ts:34` parser rejects `:`, and its catalogue has no `request_timeout` entry.
  - So alone it would show the generic fallback.
- **Skills254:**
  - Its inspection components need these catalogue entries, which exist only in Shared255:
    - `skill_inspection_unavailable`
    - `skill_history_unavailable`
    - `skill_comparison_unavailable`
    - `skill_revision_unsafe`, `skill_revision_too_large`, `skill_revision_unavailable`
  - Its own catalogue has only `:1447`.
- **Divergent JSON:** all three heads edit the same catalogue file differently, with conflicting text for the same key:
  - `lease_service_unavailable`: Shared255 has the old text, Agent250 the new.
  - `skill_agent_provenance_required` (Skills254 `:1452`) differs from PR 234's text.
- **What's needed:** a declared merge order (Shared255 before Agent250 and Skills254, or vendored entries), plus an integration check at the final combined head.

**Optional suggestions (not dropped assertions):**
- **frontend-S1 (docs):** the PR 234 contracts are no longer stated in the README; they now live only in code comments and tests. These are:
  - the keyboard boundary (Escape closes Find before the dialog);
  - the two response-code slots (`data.code` and `detail.code`);
  - the credential-prefix policy.

  Restoring them as short declarative statements would fit the README requirement.
- **frontend-S2:** there is no catalogue-wide guard against "operator" wording; c8 still has 66 occurrences. PR 227 already recorded this as follow-up; it predates these PRs.
- **frontend-S3 (modularity):**
  - **Concrete case:** `SkillWorkspace` (Skills254 `SkillFilesModal.tsx:79` onward) holds about 20 state hooks. It mixes snapshot fetching, tabs and preview, history selection, manual editing and comparison, discard and close dialogs, file import, and global keyboard capture (`:144-152`).
    - Candidate seams: a snapshot-loading hook, tab state, and a keyboard-capture boundary.
    - The separate Skills modularity review should confirm these.
  - **Minor:** `nodeErrors.ts` combines code parsing and redaction with context-specific advice. It could be split, but this is optional.

**Carried forward:** T5-S3 (installer-name asserts) and all earlier T1–T5, C4–C6 and nonpython-runtime-build findings.

## What I didn't inspect

- **Final combined head:** `1eb10a1f` itself.
- **Frozen-head copies of exact blobs:** I took several from earlier evidence (`ErrorPopup.test.tsx` is from c8) rather than re-reading them in the frozen heads.
- **GitHub249:** I didn't check its frontend beyond `nodeErrors.ts`.
- **Real-browser behaviour:** none was observed or run.