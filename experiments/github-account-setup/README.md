# Independent GitHub account setup pilot

Owner: Laomedo issue #251 / draft PR #257. Experiment branch only.
This pilots the supported flow selected in chat: explicitly choose the intended
account on GitHub for one-time private App registration, then use the existing
App's native OAuth chooser on subsequent sign-in. It does not use the device
picker, a shared App, a browser helper, or account-selection URL guesses.

## Files and outcomes

- `index.html` contains the account list, one-time setup card and live status.
- `pilot.js` renders the live owner-scoped account/App inventory, admits explicit
  setup or sign-in requests, discards late responses on navigation and renders
  all remote labels as text. No credentials or metadata are persisted by it.
- `api.js` owns fixed same-origin requests, private-session CSRF admission and
  validation of exact GitHub registration/authorization destinations. It reuses
  the feature service; it does not create an authentication implementation.
- `pilot.css` owns responsive presentation. Browser/PIN/GitHub sign-in remain
  native. The registration callback returns to the existing GitHub connections
  screen, whose current implementation owns installation, consent and Save.
- `test_api.mjs` checks the destination and request-binding invariants.
  `test_ui.mjs` checks that profile invalidation fences late navigation and private
  labels, and that rendering/setup entry never starts authorization. Supporting
  checks do not establish live GitHub registration/authorization acceptance.

## Run against the existing private preview

Requires the real private-connections implementation at `be73ad9a` or later,
including explicit `app_id` on new sign-in and private per-account provisioning.
Copy these four browser files (`index.html`, `pilot.js`, `api.js`, `pilot.css`)
into `<preview-frontend>/assets/github-account-setup/`. Open
`http://127.0.0.1:17867/assets/github-account-setup/index.html` in the existing
integrated browser. The same origin is required; do not add a proxy, export a
cookie, copy credentials, or disable admission/CORS.

If the local profile session expired, log into Laomedo privately, return to the
pilot and Refresh. No PIN, GitHub credential or browser profile belongs here.
Preparing registration does not create an App: GitHub's Create approval is still
explicit. Verify the account named on GitHub's Create button before approving.
App-owned lifecycle isolation does not mean separate browser cookie jars:
switching GitHub's active account affects its other tabs too.

For a returning account, Sign in uses that connection's saved App. A registered
App with no active connection can resume by its explicit App ID; no latest-App
fallback is used. Token-based connections are managed in the existing app.
The pilot never deletes Apps, disconnects existing accounts or changes App
visibility. Real provider validation remains pending until separately recorded.

Run supporting checks with Node 22: `npm install`, then `npm test`. An existing
pinned frontend's jsdom installation can instead be selected using
`PILOT_FRONTEND_PACKAGE=<absolute path to its package.json>`; run
`node --test test_api.mjs test_ui.mjs` without installing another dependency tree.
Review status: fully unreviewed — reviewer pending.
