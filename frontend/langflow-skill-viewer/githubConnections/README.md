# GitHub connections

The approved editable screens and user stories live in specs PR #411. The manager
shows one active screen at a time: saved accounts, account details, GitHub waiting,
repository consent, private App registration, advanced token entry or cleanup recovery.
Users never copy GitHub App configuration. Each account owns a private App,
registered through GitHub with a prefilled manifest.

`ConnectionRegistration.tsx` owns Add connection's private per-account App setup.
It requests a CSRF-admitted, prefilled manifest only after Continue, and POSTs it
only to GitHub's fixed personal registration endpoint. Each account owns its own
private App; no user copies identifiers or credentials. Registration, installation
and authorization returns remain bound to the initiating profile and lease.

`ConnectionManager.tsx` owns navigation, request epochs, invalidation and explicit
Continue navigation. It reconciles waiting attempts using read-only checks on return
and while the waiting view is visible; authorization mutations are never retried automatically. On page entry, inactive
credentials are cleaned once through the admitted cleanup action; only unresolved
removal failures show a recovery notice.
Add opens the local Continue to GitHub screen without starting registration. Only
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
GitHub registration, installation and authorization acceptance. A prepared manifest
or saved App alone does not establish a GitHub connection.

`ConnectionNavigation.tsx` supplies the same accessible Back arrow below each
connection card, with Refresh beside it where available. Account details use a
pencil beside repository access; spacing separates sections without heavy rules.
Token hints live in the masked input placeholder while its accessible name remains.
Saved connections update in place without a persistent success banner.

Browser consent offers the configured App installation page for missing repository
access. The fixed GitHub URL carries only the pending request identifier. Returning
from GitHub refreshes that same lease-bound browser inventory; provider query
parameters never grant access. Save remains the explicit local consent boundary.

Ordinary Add never selects the latest profile App. Existing reconnect selects its
own saved App. A matched installation return may continue authorization only for
an onboarding attempt created by a completed registration; ordinary waiting
attempts still require Continue. Returning browser consent only refreshes candidates.

First-time setup presents two numbered steps: choose the intended account using
GitHub?s profile menu, then Continue to submit the private manifest. The external
GitHub link opens separately so setup stays available. Returning connections keep
their saved App; setup never silently borrows another account?s App. Registration
uses the shared Button, navigation, theme tokens and responsive connection card.
