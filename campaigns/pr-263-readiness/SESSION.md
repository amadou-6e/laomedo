# Native profile browser checks, 2026-11-10

Sources: profile tracking `7bfeffb0`, logout coordination `ce19d9a5`.
Fresh pinned frontend `fec71dca` with task overlay, built using Node22.23.3.
Only a separate task-owned Edge profile and synthetic QA PINs were used.

Observed actual app behavior: profile creation201 and upstream login200; session
restoration on reload and browser restart; community link opened a popup without
the unsupported optional tracking PATCH. An injected logout network abort stayed
unconfirmed and Check current profile restored the live session.

The first two-tab switch exposed a missing broadcast after upstream logout
cleanup unmounted the menu. After `ce19d9a5`, switch returned both tabs to the
picker. Wrong PIN checks returned four401 responses then a real429, cleared the
PIN, and displayed/disabled controls for the server-provided60second delay.

Screenshots and runtime logs are outside Git in the task readiness directory.
TypeScript remains failing with652 diagnostic lines, none in the profile files;
the same count was present in the pinned baseline. Production build succeeds.
These observations do not establish all profile acceptance, owner approval or
Claude review of the latest correction; those remain pending.

## Visual corrections at 0c0d8d91

The profile picker now preserves exact case, the sign-out popup has a visible
accessible Close control, and uncertain-session copy is intent-neutral. The real
isolated Edge check observed duplicate-name409 and reserved-name409. It fetched
an actual successful creation201 then lost the browser response, reconciled the
saved profile through the list and entered it without creating a duplicate.
The PIN cleared; the Close control dismissed only the notice, and a390px picker
preserved the stored mixed-case profile names. Screenshots remain outside Git.
The browser script is visual-recheck.cjs. It is experiment evidence, not a
production test or complete acceptance. App restart/expiry/bfcache and requesting
owner inspection remain unfinished. Reviewer V1/V3 focused recheck is pending.


V4reviewerfoundadjacentrecoverybuttons. Sourcea0e04a96206803ddcb4954b3309343e84baf2b73 usesexplicitflexcolgap4. Freshpinnedbuildpasses; Edgeallpreviouschecksrepeatedpassplus390create/enterformswithnoPINincaptures. Claude focusedrecheck base db2c43f3/head a0e04a96 APPROVE implementationandcapturedvisualstates;V1-V4verifiedfixed,N1upstreamautoLogin guardresolved. No furtherV1-V4rechecksrequired. Apprestart/expiry/bfcache/ownerinspectionremainopen; nooverallreadyclaim.

## Remaining lifecycle evidence, 2026-11-11

At unchanged production head a0e04a96206803ddcb4954b3309343e84baf2b73, lifecycle.cjs created a new synthetic profile and observed authenticated restoration after the actual native service was stopped and restarted against the same runtime. Before: launcher28224, Python30776/service34052; after launcher3864/Python33488. Separate startup logs record10:25:36 and10:31:11 Europe/Berlin. Runtime logs and marker files stay outside Git. The marker alone is not proof of restart.

short-expiry.ps1 derives the production launcher but binds the exact task checkout and sets experiment-only supported10s access/15s refresh lifetimes, new state and port17868. Normal production launcher/configuration is unchanged. expiry.cjs creates a synthetic profile, waits25s and reloads; real expiry returned Choose profile with no PIN form. PIN exists only in memory.

The first navigation test did not enter cache, and its synthetic pageshow event is supporting-only. back-cache.cjs removes Playwright default cache disabling. Actual navigation away/back reported realCacheRestore:true, then navigation type reload from the production handler; authentication restored.

Same Claude session reviewed logs/harnesses and opened expired picker/restored captures: expiry and bfcache gaps closed. Observable restart accepted with lowE1 request for independent process/startup evidence, supplied in ignored263-restart-process-evidence.md. OptionalE2 capture shows authenticated header/loading, not settled workspace. Owner inspection and specification/stack gates remain. No source changes, whole-feature approval or production merge is implied.

## Owner entry-presentation feedback, 2026-11-11

The owner created a profile and logged in, requested plain validation language without technical details and decorative profile icons, and clarified that valid matching input does not trigger validation. The owner separately selected local profiles now/private revocation later. Implementation dc8d1e5a40734503c5e02b30cb1bacecf8cd3f38 simplifies shared copy, omits technical diagnostics on profile entry, clears local validation on edits and prior-screen errors on navigation, and adds aria-hidden person icons while preserving names. No validation/authentication policy change.

Real Edge check entry-feedback.cjs used the actual17866app, no mocks/PIN entry/profile writes. Observed six stored-profile icons, new plain blank-submit message, no diagnostic expander, alert clearing after edit and a390px picker. Four focused frontend regressions pass, final Node22 build1m24 passes, all8CIchecks pass. Screenshots/runtime logs stay ignored and outside tracked evidence. User session was not altered by the independent browser check. Revised UI owner acceptance and same-session Claude review are pending; do not claim readiness.
