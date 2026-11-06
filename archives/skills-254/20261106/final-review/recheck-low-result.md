# PR254 Skills: final recheck at head `82fbda3c`

This was a low-effort, focused recheck. I read the ledger, the code part of `final-delta.diff`, all of `current-docs.diff` (docs, the five flow hunks, and the deletion headers), the preservation manifest, and opened eight new screenshots. I did not reread the old stack.

## ID dispositions

| ID | Disposition | Basis |
|---|---|---|
| **B-Q2 / F-Q2** | **Fixed** | `manual.py` `_require_publication_base` walks the candidate's parents and raises `skill_manual_stale` if `expected_latest` is not among them. It only runs for a new publication row; a retried row is still protected by the compare-and-swap in `promote_draft`. The negative test re-reads the refreshed latest and shows both the external promotion and the candidate head survive. The stale catalogue text no longer tells the user to "Publish again". |
| **B-Q3** | **Fixed (blocked state reported as uncertain)** | `promotion_busy` is no longer mapped to stale in `handler.py`, so it now surfaces as `unavailable`. A test shows the same request promotes once the blocker clears. Lock handling is a documented maintainer procedure, not automatic recovery. |
| **B-Q1, B-Q4, B-Q5** | **Accepted as documented constraints** | Covered in the operations README and the `skill_operation_refused` recovery text, which names Base Commit. |
| **B-S2** | **Fixed** | The lease test is restored exactly to develop. |
| **B-S1, B-S3** | **Accepted as non-blocking** | Rationale recorded in the ledger. |
| **F-D1** | **Fixed** | All six read codes and the related operation codes are committed to the catalogue, and the installer now copies `ErrorExplanation.tsx`. A Python key-coverage test was added. The isolated 516 frontend cases pass (claimed). |
| **F-Q1** | **Fixed** | `sourceChanges.ts` maps Monaco edit ranges back onto the original text. That keeps the leading BOM and any line endings outside the edited range, and edits apply in reverse order of position. `SkillSourceEditor.tsx` now builds the saved text with it instead of `getValue()`. Tests cover BOM files, mixed line endings, reversing an edit, simultaneous edits and multiline edits. |
| **Redaction** | **Fixed** | `credentialPrefix` (`sk_`, `gh*_`, `github_pat_`) is now applied to error codes as well as node IDs. |
| **F-D2** | **Fixed** | SK-08 now says delete is immediate with Ctrl+Z/Ctrl+Y, and the explorer guide and manual workspace guide agree. |
| **F-S1, F-S2, F-S4** | **Fixed / accepted** | |
| **F-S3** | **Mostly fixed** | The guides are now declarative and archives point to exp `d056ff3d`. One residual issue (R-S1 below). |
| **F-Q3** | **Accepted** | Creating files or folders directly is documented as unsupported, and the Search wording now says "working". |
| **V-Q1, V-Q2** | **Accepted as intended** | Per your decisions. |

## New findings from this delta (none blocking)

- **R-S1 (docs, low): leftover evidence pointers and stale wording.**
  - SK-06, SK-08, SK09 and SK10 in `user-stories.md` still say the "revision-specific/actual evidence is in `manual-workspace.md`", but that guide no longer contains any evidence.
  - Step 4 of the walkthrough still says "File browsing is read-only".
  - SK-04 and the navigation guide say the comparison is against the "saved working head". The code actually compares against the working buffer, including unsaved edits.
- **R-Q1 (low, newly exposed):** a lingering lock now leaves a publish request uncertain indefinitely. While a request is pending, `requestClose` refuses to close the workspace, so the user can only leave by reloading the page. The documentation for this is acceptable. Please confirm the behaviour is intended.
- **R-S2 (low):** `test_graph.py` and `test_sources/test_graph.py` now `import langflow` after only checking that `lfx` is installed. If `lfx` is present without `langflow`, these tests error instead of skipping.
- **R-Q2 (low, spec):** after a divergence, publishing from the journal stays blocked until a maintainer reconciles it, but no concrete procedure is documented. Two possible routes are rebuilding the journal or promoting a journal revision.

## Flow hunks and example preservation

- **Flow hunks:** all five previously unread flows have the same two-hunk change. The embedded `LaomedoSkill` code is replaced by the hidden-legacy and Advanced Revision version, and `code_hash` changes from `1eedfda82fd9` to `6b6011d7c9bd`. Nothing else changed.
- **Example preservation:** the 10 deleted files match the manifest's 10 blob and exp-location entries. I could not verify the blobs on exp without git; the manifest's claim is evidence, not my own check. `examples/graph.py` is retained; `.gitattributes` no longer lists the deleted folder.

## Visual review (isolated captures)

What the captures show:
- **Dirty workspace:** a modified-file marker, and the "1 file to publish · Discard · Publish" footer only while there are changes. Compact and nothing overflows.
- **Discard popup:** centred with Keep editing and Discard changes, without shifting the editor.
- **Search:** the folder/file/line tree, with the match highlighted in the source.
- **Inline rename:** the filename stem is selected inside a blue-bordered field in the row, with the JSON braces icon.
- **Empty folder:** labelled "references (empty · not saved)", with three history entries.
- **Source failure:** the failure text appears directly below Source, with no Discovery heading. Advanced settings is collapsed.
- **Empty Source:** shows "No source found".

Visual issues:
- **V-Q3 (open):** in `isolated-fullpage.png` the Restore icon is showing, but the dialog spans about 1272×810 of a 1440×960 viewport. It does not fill the page. It may have been captured mid-transition, but as captured it does not show a full-page state.
- **V-S1:** in `isolated-source-empty.png`, the node and sidebar icons are still grey placeholders, so it was captured before the icons finished loading. The open dropdown also hides the Advanced settings row.

Not reopened this turn: the history, binary and outage PNGs in this directory. I relied on the identically named images from the earlier review.

## Verdicts (bound to head `82fbda3c`)

- **Implementation: APPROVE.** All blocking mechanisms (B-Q2, B-Q3, F-D1, F-Q1) are fixed, and I found no interaction regression in the changed callers: the publish path, the handler mapping, the editor change listener, and the catalogue lookup.
  - The test totals (127 Python, 516 frontend), the 8 CI checks, served-source proof and wheel parity are claims; I did not open `final-served-source.json`, `standalone-wheel.json` or `recheck-native-failure.json`.
  - Full TypeScript has 265 diagnostics, reportedly none in Skill files. That is not a green typecheck.
- **Specification: APPROVE with non-blocking fixes.** R-S1 and R-Q2 are documentation follow-ups.
- **Visual: INCOMPLETE.** V-Q3 needs a settled full-page capture, and the empty-Source capture should be retaken with icons loaded.
- Your own final workflow validation, and any merge, remain separate gates.

## Not read

- The documentation hunks in `final-delta.diff`: deleted dated assets and narrative rewrites, beyond what `current-docs.diff` shows.
- The bodies of the deleted examples.
- Any exp contents.
- The served-source, wheel and failure JSON files named above.