# Integration finding ledger

Exact source merge:8fe9e364..d3d06e3a, with develop6077e79a as second parent. Tests-only corrections:f38e4b70. Docs-only:97ea2c3c. Installer correction:2a8a764218117674977e39455ea6c305ebc8614b. Same read-only reviewer conversation, low effort.

| ID | Type / severity | Disposition | Evidence / next action |
| --- | --- | --- | --- |
| C-01 | Confirmed defect / low | Corrected; focused recheck pending | Profile stage validates all existing anchors before copying assets or writing target files. Missing auth/password/picture/tracking anchor controls preserve every file and create no assets. Actual pinned-source output across17files byte-identical. c01-correction.diff, c01-final-checks.log, c01-pinned-output.json. No claim of atomicity on arbitrary filesystem I/O failure or entire parent overlay transaction. |
| D-01 | Docs / low | Corrected as requested | Backend README says React entry is implemented and actual browser acceptance unverified. No repeated wording review required. |
| D-02 | Docs / low | Corrected as requested | Consolidated picker descriptions retaining avatars, names, chevrons, divider, validation clearing and ARIA details. |
| Q1 | Question / Graph private method | Closed by reviewer packet2 | Installed and pinned Graph method exists atline1523. |
| Q2 | Question / no-feedback call | Closed by reviewer packet2 | Feedback=None explicitly refuses; caller roundtrip only invoked with edge. |
| Q3 | Question / malformed raw Message dict | Not escalated by reviewer | Unsupported malformed input corner, no new requirement introduced. |
| Q-P1 | Question / unknown profile mode signout | Evidence supplied; classification pending | Logout disabled until ready, switch exists only when enabled. Failed mode check setsfalse and allows ordinary logout without profile broadcast. This fallback is unchanged develop behavior; no new private-profile authority is enabled. |
| Q-P2 | Question / multiselect dependency | Evidence supplied; classification pending | Options is parent prop; effect sets only local state, not parentcallback. Child local rerenders retain same prop reference. Inspect deployed pinned source and caller. |
| Q-P3 | Question / installer import API | Evidence supplied; classification pending | Maintained caller search finds only script CLI; no supported import-module entrypoint. tools directory on sys.path for documented invocation. |
| Q-P4 | Suggestion / stale display subscription | No behavior change proposed | Parent develop behavior, display only, not dispatch. |
| Q-P5 | Question / case reconciliation | Evidence supplied; classification pending | Model trims and retains case; registry passes request.name to upstream and returns created.username. Casefold rejects duplicates only. |

Core packet1 partial; packet2 partial with C01; packet3 readall1609remaininglines with listed questions. Generic imports packet running. Tests/maps/docs integration still fully unreviewed ? reviewer pending. Current Skilldefault/Advanced, connectedPriorRun and single-port PR layout captures independently APPROVE; missing profile/recovery views and actual native workflows retain their declared limits.
