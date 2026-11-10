# Native private-admission controls, 2026-11-10

Source: Laomedo private-admission working tree subsequently committed as
`2b66485a`, before dependency merge `3c46808b`. These are experiment harnesses,
not production tests or full feature acceptance.

`vault.py` uses one new synthetic broker-owned UUID, stores a synthetic value,
loads it through a new native vault instance and verifies removal. It does not
enumerate or touch other Windows Credential Manager entries.

`admission.cjs` uses the separate task-owned Edge profile `readiness/private-browser`
and app at 127.0.0.1:17867. It creates a disposable QA profile with a random PIN
held only in memory. Actual results: unauthenticated readiness 403; explicit
upstream login then readiness 200/ready; private cookie HttpOnly/persistent/Lax;
logout 200 and replay of the old in-memory JWT plus lease refused with 409.
No GitHub credential, private repository content or model task was used.

Runtime state, cookies, PINs and raw logs stay outside Git. Final-head restart,
real GitHub modes, consent, private files and all SC10 acceptance remain pending.

## Native connection manager, 2026-11-10

Production head aa0d3704 (HTTP adapter1c035eef). The actual native Windows app was
restarted on its task-owned17867 runtime; other apps/runner were preserved. The
real isolated Edge browser created a fresh synthetic PIN profile, entered normal
upstream login, opened Settings/GitHub connections and received an empty owner
index200. A deliberate POST without CSRF was refused409 private_request_refused
before any credential submission. App setup rendered with the fixed callback.
No GitHub credential, vault credential write, authorization exchange or model
turn was used. Screenshots and logs remain outside Git. manager.cjs owns this
bounded observation. A first browser invocation preceded server readiness and
received connection refused; after startup the same non-model check passed.

The final pinned frontend build passed in2m2s; three UI controls cover synchronous
credential DOM clearing/cancel and unselected repository consent. Those controls
and this empty manager observation do not establish real connection or private
Skill acceptance. All new HTTP/UI/lifecycle/reader work is fully unreviewed -
reviewer pending. Claude's current packet is rate-limited until19:20 Berlin.


## Reviewer correction check, 2026-11-10

Claude manager review ataa0d3704 foundM1: a new BroadcastChannel sender delivered
to another channel in the same document, invalidating its own mutation epoch.
Fixbabdd226 tagsmessages and ignores the manager's own source. Two new frontend
controls exercise real same-document object delivery and reject another document's
late result; total5UIcontrols pass. Also correctedM2timeout/uncertaincopy,
M3registrationlinkstyling andM4copy. Clean reviewed profile parenta0 integrated
as8a858b30, unchangedownpatch. Complete matching frontend build2m10s passes.

Actual native synthetic-profile UI posted an invalid-format synthetic token,
received400, displayed the supported-token refusal in its initiating document,
retained no credential inputDOM and showed no false another-tab notice. The
invalid format is rejected before provider transport/vault custody. No real
GitHub credential or exchange was used; this is a native UI mutation control,
not positive GitHub integration acceptance. Manager harnessfirstpointed at a
profile-only catalogue and then expected a non-rendered catalogue title; those
checks failed, were diagnosed and rerun with the matching catalogue and actual
shared-presenter description. Current manager.cjs records the successful check.
Screenshots/logs remain outsideGit. M1-M4focusedrecheckpending: same reviewer
hitquota on nextpacket, resets21:00Berlin. Private Skillaccess stillunfinished.
