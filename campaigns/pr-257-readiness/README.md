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
