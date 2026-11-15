# GitHub connections

The approved editable screens and user stories live in specs PR #411. The manager
shows one active screen at a time: saved accounts, account details, GitHub waiting,
repository consent, advanced token entry, unavailable sign-in or cleanup recovery.
Normal users never enter GitHub App configuration. Browser sign-in requires an
operator-configured App; missing provisioning is shown honestly as unavailable.

`DeploymentSetup.tsx` owns the deliberate local deployment entry
`/settings/github?deployment=1`. Its button requests a CSRF-admitted manifest and
POSTs it only to GitHub's fixed personal App registration endpoint. It never
receives the returned App credential and is not part of ordinary Add Connection.

`ConnectionManager.tsx` owns navigation, request epochs, invalidation and explicit
Continue navigation. It reconciles waiting attempts using read-only checks on return
and while the waiting view is visible; authorization mutations are never retried automatically. On page entry, inactive
credentials are cleaned once through the admitted cleanup action; only unresolved
removal failures show a recovery notice.
Add prepares an attempt and waits on the local Continue to GitHub screen. Only
pressing Continue navigates the current tab; GitHub returns directly to repository
consent without leaving a second Laomedo tab. Repository search is shown only
when more than five repositories are available.
Disconnect confirmation uses that connection's cleanup status. Profile-wide
cleanup failures remain a separate recovery notice, without labelling the selected account's successful deletion a failure.
Repository editing initially selects the saved repository IDs that remain in the
verified inventory; new connections start unselected. Expired sign-in returns show
explicit recovery rather than a generic failure, without replaying authorization.
`ConnectionAccounts.tsx` renders the account list and selected account details.
`ConnectionForms.tsx` owns masked advanced token entry and clears it synchronously
before submitting or cancelling. Its inline variant is mounted only while the
advanced disclosure is open, so collapsing it discards the secret. `ConnectionInventory.tsx` owns explicit repository
selection and search. `connections.css` scopes the approved spacing and responsive
panels to this feature. `types.ts` owns wire records; `api.ts` owns bounded requests,
CSRF acquisition and fixed-origin authorization URL validation.

Private metadata is cleared on failed requests, unmount and cross-tab invalidation.
Late requests cannot restore stale state. The server revalidates the profile lease
and resource generations independently. UI status is saved metadata, never proof
of present GitHub permission. Repository editing verifies the existing credential
and account before creating a new consent attempt; it does not request sign-in
unless that credential needs replacement. Disconnect fences access before cleanup.

The preview and independent review must distinguish rendered UI checks from real
GitHub authorization acceptance. Secure automatic deployment provisioning remains
unimplemented; the UI must not pretend to have established a GitHub connection.
