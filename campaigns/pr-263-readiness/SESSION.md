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
