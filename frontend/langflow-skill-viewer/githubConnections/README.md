# GitHub connections

The approved editable screens and user stories live in specs PR #411. The manager
shows one active screen at a time: saved accounts, account details, GitHub waiting,
repository consent, advanced token entry, unavailable sign-in or cleanup recovery.
Normal users never enter GitHub App configuration. Browser sign-in requires an
operator-configured App; missing provisioning is shown honestly as unavailable.

`ConnectionManager.tsx` owns navigation, request epochs, invalidation and automatic
browser launch. It reconciles waiting attempts using read-only checks on return
and while the waiting view is visible; mutations are never retried automatically.
`ConnectionAccounts.tsx` renders the account list and selected account details.
`ConnectionForms.tsx` owns masked advanced token entry and clears it synchronously
before submitting or cancelling. `ConnectionInventory.tsx` owns explicit repository
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
