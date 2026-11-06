# Skills254 finding ledger ? head82fbda3c, base37dc9aa9

Only Skills is selected. Shared255, GitHub249 and Agent250 are deferred; no other production branch changed. Same Claude session reused.

| ID | Disposition awaiting recheck | Evidence |
|---|---|---|
| B-Q1 | Documented exact Base Commit under Advanced for backfilled heads; operation-refused recovery names it. Blank commits remain initial-root-only, deliberately fail closed. | operations/README.md; catalogue |
| B-Q2 / F-Q2 | Confirmed by failing negative test. Fixed ancestry guard prevents refreshed expected_latest overwriting an external promotion, preserving candidate and latest. Single durable journal per registry is explicit; automatic external-history merge unsupported. | manual.py; test_refreshed_latest_cannot_publish_a_divergent_candidate; publication-checks.log |
| B-Q3 | promotion_busy now remains uncertain rather than falsely stale. Exact request safely reconciles after blocker removed. Locks never auto-expire/delete; explicit stopped-writer maintenance constraint documented, not automatic recovery. | test_busy_publication_reconciles_same_request_without_claiming_stale; operation README |
| B-Q4 | Hidden saved-graph compatibility deliberately retained: root instructions require preserving external payloads; removed from all new authoring surfaces. Explicitly documented. | operations/README.md; actual Source captures |
| B-Q5 | Journal recreation is not identity-preserving recovery; registry+journal backed up together. Non-root registration truthfully records new event IDs, not invented original provenance. | operations/README.md; import-history.md |
| B-S1 | Test-only source locator retained for two legitimate source layouts; no runtime fallback or extra deployed catalogue. No production dependency on Shared. | support/paths.py |
| B-S2 | Unrelated host lease tests restored exactly to develop; absent from PR own-diff. | final-delta.diff |
| B-S3 | Optional orphan-draft cleanup / missing-commit classification not changed; no overall completion of generic registry maintenance claimed. | current source |
| F-D1 | Missing Skill read-error catalogue entries and exact shared helper now committed here; no Shared prerequisite. | 8938 and a67 commits; 516 frontend checks pass |
| F-Q1 | Range-based text projection preserves BOM and untouched mixed endings; inserted/replaced bytes follow editor input. Four exact-byte tests include inverse edits and simultaneous/multiline ranges. | sourceChanges.ts / test; SkillSourceEditor.tsx; frontend-final.json |
| F-D2 | Immediate delete+undo and local empty-folder retention now consistent in guides/stories. | current-docs.diff |
| F-S1 | Added explicit read-code catalogue coverage alongside actual presenter regressions and installed-module guard. Missing entries reproduced as41 failures, redaction gap14; all fixed. | frontend-jest*.json; test_errors.py |
| F-S2 | Shared helper is exact extracted source. Existing Popup duplication is nonblocking; no broad error framework rework. | ErrorExplanation.tsx |
| F-S3 |34 exact dated files archived on expd056ff3d before cleanup.26 added datedPNG assets removed from production. Guides now declarative. Older base docs screenshots remain explicitly historical. | archive manifest; current-docs.diff |
| F-S4 | Deleted example gitattributes rule removed. examples/graph.py supports maintained Skill builders; no new domain runtime. | current-docs.diff |
| F-Q3 | Direct create-file/folder is unsupported and documented; owner requested preserving empty working folders, which real drag/drop verifies. Search now says working, not pinned current. | explorer guide; real-skill-files-result.json; SkillSearch.tsx |
| V-Q1 | Equal old/current indices intentionally share a gutter cell; changed lines use two cells, insertions have no old index. | SkillFileDiff.tsx FileRows; real-skill-history-settled.png |
| V-Q2 | Error card is viewport-owned by earlier user request, deliberately outside dialog boundaries; actual1024x720 bounds pass. | real-skill-recovery-result.json |

## Isolated evidence

Clean pinned Langflow fec71dca overlay installer passes from Skills alone. All127 Skills tests pass; three Windows symlink tests skipped. First independent test run hit upstream compatibility import order; explicitly initializing required Langflow before lfx fixed it, no runtime behavior workaround. All516 cases/23 frontend suites pass. Vite production build passes; exact-head rebuild is frontend-head-build.log. No other PR source used.

Actual Edge on separate17861 app,18783 source,18788 operations: real initial import; editing/promotion; selected-file history; search/fullpage/discard; text+PNG+JSON imports; inline rename/drag/drop/empty folder; delete/undo/redo; clipboard; byte-exact binary promotion; Source failure+recovery; service stop+restore and retained history. Real reference added via authenticated manual operation (not model/provider fixture), because direct folder creation is explicitly unsupported. Private registry has four real commits. No model, Agent or GitHub run. Auto-login app does not establish profile restoration, expired-auth or account session-management acceptance.

## Remaining review scope

Complete focused corrections above and previously unread changed flow.json code_hash hunks; deleted examples have10/10 exact Git blobs on exp (deleted-example-preservation.json). Current docs supersede old narratives. Full substantive review still must state unread scope. Owner validation is pending; no merge authorized by this ledger.
