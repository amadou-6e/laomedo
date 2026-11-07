# Agent PR250 validation, 7 November 2026

This archive contains real provider/browser observations and scoped independent reviews. It is evidence, not a portable authenticated runtime or a claim of whole-PR acceptance. PR250 remains draft, pending remaining review and owner inspection. The production change lives on refactor/205, based on develop bb250135; experimental harnesses live on exp under work/agents250-final.

## Observed stories

- Real Codex, Claude and OpenCode Fresh: read the actual repository README and return a useful summary. Native Activity is visible. Initial Fresh observations predate later capture/HTTP/recovery corrections; source bindings below distinguish these checkpoints.
- Saved-reference Fresh?Resume: each provider retained one native session, two native turns and distinct Activity attempts; connected Prior Run survives graph import/reload. This does not establish a same-node run selector.
- Actual graph Stop: all three providers were cancelled after native command startup and reported confirmed cleanup. The earlier per-node Run-button probe was invalid and is explicitly retained as invalid, not counted as Stop evidence.
- Controls: keyboard/mouse Advanced disclosure, persisted choices, real model refresh for all three providers, selected model preserved and no agent submission. Model recovery fix01e8a3db is already on develop and in the candidate.
- OpenCode linear capture: one new actual read-only run at7ca74370 retained66 raw ACP updates and62 text deltas, matching the answer. Current usage projection was separately applied offline to those immutable actual receipts. The live run was single-step; multi-step aggregation has unit coverage only.
- Local runner recovery at02c2c291: offline error, copy control, spinner/Cancel, bounded card, Start?ready13.419seconds, green connection contour, dismiss, no graph/model rerun. Actual startup cancellation took24.096seconds and confirmed no listener. Three real overlapping-status Start cycles succeeded after the Docker readiness race fix. The first uncaptured Start failure's exact cause remains unknown; the later reproduced race is a separate established mechanism.

## Revision binding and limits

Stable graph/Advanced/Activity screenshots and frontend deployment bind to4b81988b; later changes to frontend are README-only. Resume, initial Fresh/Stop and earlier recovery observations retain their own original checkpoints in the reviewer reports; do not relabel them as rerun on the handoff head. Final runtime source differs from02c2c291 only in offline migration tooling; later commits clarify a README and restore a test. Full586-Agent test run and340-file installed-wheel parity bind to2e2be4c6. See check-summary.json for exact revision and scope.

No browser screenshot or internal fixture establishes authentication lifecycle, provider isolation, complete evidence or owner acceptance. Claude evidence-completeness remains unknown. The OpenCode live path used the supported dedicated OpenCode Go profile injection, not the default Console/OAuth loader. App-owned OAuth, default Console sign-in, split executor, new child capture and Docker-down/uninstalled paths were not retested here. Native GitHub mediation remains separately scoped to issue215; generic HTTPX follow-up is issue203. Full TypeScript checking remains inherited red:259 candidate diagnostics versus265 accepted, with zero added normalized diagnostics; the frontend build and86 focused tests pass.

## Reviews and unresolved gates

Each report names actually inspected revisions/ranges; approval is scoped, never a reusable whole-PR boolean. The final boundary-test review identified T-D1: a lost duplicate-key catalogue assertion. It was restored in e27f1c92 and23 error tests pass, but the required focused reviewer recheck did not run because Claude hit its five-hour limit (reported reset20:40 Berlin). Provider and shared test-source packets and final integration coverage are unfinished. Existing23 checkpoint PRs remain on HOLD; this archive does not authorize closure. Spec403 remains draft; its one stale214?250 implementation link was corrected at558d7e2 without changing maturity. The user's original fix/407 edits were restored and Git contents verified with CRLF normalization.

Source LOC is not reduced: tracked src Python/MJS grows33,247?37,922 (+4,675), excluding tests/docs/frontend. This was reported to the owner. No size-parity claim or implicit waiver is made.

Manifest hashes describe the archived bytes. PNGs and safe summary JSON are curated; no credential stores, raw native logs, private DBs, browser storage or full profiles are included. Existing private runtime remains local. Harnesses on exp are bounded validation tools, not production services or permanent authorization caps.
