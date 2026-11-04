**CODE verdict: REVISE.** The restored production code matches the pr-213, pr-214 and pr-234 originals, and in the combined head it sits alongside the newer features without replacing them. Two fixes are needed: four pr-234 native-timeout tests are still missing, and the user-stories doc contains leftover patch markers. Neither change touches runtime code.

## Findings
1. **Medium – missing old contract.** Four tests from `originals/pr-234/frontend/langflow-skill-viewer/nodeErrors.test.ts:4-34` were not restored:
   - `native request timeout keeps its safe method code and descriptive recovery`;
   - `native timeout parsing rejects arbitrary method payloads`;
   - `ACP %s timeout preserves its code…` (for new, load, set_config_option and cancel);
   - `ACP timeout method allowlist excludes execution tunnels and payload suffixes`.

   The production change they protect is restored (`shared-ui.diff:867-869, 877-878, 887, 896, 914`). The only remaining check is `nodeErrors.test.ts:222`, which only confirms a bare `request_timeout:session/new` keeps its code. Nothing now tests these risky paths:
   - the widened `failed: (\S+)` message parser;
   - mapping to the `request_timeout` description and recovery;
   - `isKnownNodeError` for timeout codes;
   - rejecting `request_timeout:https://private-token…`, `session/exec` and `session/new?secret=private`.

   **Fix:** restore those 34 lines.
2. **Medium (docs) – patch artifacts.** `skills-followup-206/docs/features/skills/user-stories.md:50-61` begins each line with a literal `+`. The new acceptance criteria will render as stray `+-`/`+` text instead of list items. **Fix:** remove the leading `+`.
3. **Low – the two PR heads differ from the combined head.**
   - Combined `PopupFrame.tsx:19-64` correctly contains both sets of behaviour: the modal-scoped stacks, popover, global-vs-modal hiding and Escape `stopImmediatePropagation`, plus the restored green border, `max-height:300px` spacing and focusable scroll region.
   - Each branch alone lacks one set: Shared `PopupFrame.tsx:39-44` has no modal-scoped stacks, and Skills `PopupFrame.tsx:61-63` has no viewport/scroll changes.
   - Both branches edit adjacent lines, so whichever merges second will conflict. That conflict must be resolved exactly as in combined 698f33d8.
4. **Low – no duplicate-key guard for the catalogue.** `JSON.parse` silently keeps the last duplicate key, which would overwrite a current description. I checked 11 high-risk appended keys (including `request_timeout`, `local_source_not_allowed` and `skill_operation_refused`) and none is duplicated, but no test enforces this.
5. **Info – inherited from pr-234, not a regression.**
   - **Paused cross-flow canvas:** when a cross-flow read is paused offline, `isFetching` is false while `isPlaceholderData` is true. The canvas therefore shows the new flow with the previous flow's build history (`upstream.patch` guard; `CanvasQueryState.test.ts:132-139` records this).
   - **Comparison failure copy:** the comparison recovery text says "Select Current source…" while the button is labelled "Reload files". This matches the original and is not unsafe.

## Confirmed correct, from source comparison
- **Shared error presenter:** `ErrorExplanation.tsx` and `SkillInspectionError.tsx` are byte-equivalent to pr-234.
- **Reload rules:**
  - Refusals never offer Reload: `invalid_skill_id`, `immutable…`, and `skill_revision_unavailable`/`unsafe`/`too_large`.
  - Unknown file, history or comparison read failures reload only the same selection's GET. The tests assert identical URLs and no `post`.
  - The missing skill/revision case now uses catalogue codes, and all four of those keys exist in the combined catalogue.
- **Redaction:**
  - Only the `code`/`detail.code` slots are read.
  - The `sk_`, `gh[pousr]_` and `github_pat_` filter now covers both unknown codes and node IDs, case-insensitively.
  - Native timeout codes are checked before the credential filter, so an allowlisted timeout code keeps its method suffix in diagnostics.
- **Combined `nodeErrors.ts`:** keeps the versioned GitHub envelope parsing (`:46-68`) next to the restored lines, so it was not overwritten wholesale.
- **Canvas guard:** the `upstream.patch` hunk and `CanvasQueryState.test.ts` are identical to pr-234.
- **Keyboard adaptation:**
  - Source stops propagation of every key except Escape. Ctrl+F is claimed by the workspace's capture handler (`SkillFilesModal.tsx:144-152`), which correctly replaces the removed "Find in file" button.
  - `editContext:false` and the editable `readOnly:false` are preserved.
  - I found no bubbling save shortcut that would be blocked.
- **Recovery popup:** the `recovered` prop matches pr-214 line 38, and the PopupFrame changes match pr-213 lines 39-44.
- **Catalogue tests:**
  - The catalogue-wide `test.each(Object.keys(catalog))` (`nodeErrors.test.ts:26`) covers all new entries.
  - The Python producer guards (`test_inspection/test_errors.py`, recursive `SourceError` in `test_sources/test_errors.py`) read the actual source files. The single `skill_file_missing` exemption is the documented private projection.
- **`test_preimages.py`:** uses literal IDs and checks payload order, the persisted `json.dumps(record)` and the head value. It does not derive expectations from the current serializer.
- **Installer:** copies the named `SkillFilesModal.test.tsx` beside `SkillFilesModal.tsx` (its import is not rewritten to `./index`), plus the `SkillInspectionError` pair and `ErrorExplanation.tsx`. The `CanvasQueryState.test.ts` destination is `PageComponent/__tests__/`, with no `mkdir`. I couldn't confirm that folder exists in the pinned Langflow tree; the pending 698f build should settle it.

## Read scope
- **Diffs, read in full:** `shared-ui.diff` (1–1162) and `skills-ui.diff` (1–736).
- **pr-234 originals:**
  - `ErrorExplanation.tsx` and `SkillInspectionError.tsx`, in full;
  - `nodeErrors.ts`: the `safeCode` and timeout regions;
  - the full test list of `nodeErrors.test.ts`, plus its lines 1–37;
  - the test list of `ErrorPopup.test.tsx`;
  - `SkillFilesModal.test.tsx` lines 60–107;
  - `CanvasQueryState.test.ts` lines 60–112;
  - grep checks of `SkillHistory.tsx`, `SkillFilesModal.tsx`, `upstream.patch` and the three viewer catalogue entries.
- **pr-213 and pr-214:** grep checks of `PopupFrame.tsx` (pr-213) and `RecoveryPopup.tsx` (pr-214).
- **Current trees:**
  - Shared, Skills and combined `PopupFrame.tsx`, in full;
  - combined `nodeErrors.ts`, by grep;
  - parts of combined `nodeErrors.test.ts`;
  - Skills `SkillFilesModal.tsx` lines 40–164;
  - the keyboard-handler sweep of the Skills overlay;
  - installer grep;
  - the `+` lines in Skills `user-stories.md`;
  - spot checks of the combined catalogue keys.
- **Not read:**
  - pr-214 `RecoveryPopup.test.tsx` and pr-234 `SkillHistory.test.tsx`/`SkillInspectionError.test.tsx`; I checked the restored versions in the diffs instead;
  - `original-commit-preimage-records.json`, so the literal IDs in `test_preimages.py` are not cross-checked against the old writer records;
  - the logs and JSON files.

I ran nothing. Jest, the Python suites and the 698f build were not re-executed or confirmed here.

**VISUAL / real-browser acceptance: still PENDING.** That needs the remaining Jest suites, real browser stories, actual screenshots and owner inspection. I give no verdict on retiring all 23 PRs or on any merge, and this does not approve full features or providers.
