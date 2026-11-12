# Private GitHub connection manager

`ConnectionManager` renders the canonical C01-C14 connection states inside native
Settings. It owns temporary form values and selected repository consent, clears
credential fields before awaiting a request, and never stores them in browser
storage. `ConnectionForms` owns masked app and token entry. `ConnectionInventory`
shows verified candidates and explicit consent; no repository starts selected.
`types.ts` defines public wire records, separately from rendering. `api.ts` owns
bounded same-origin requests, obtains a private-session CSRF proof in memory and
projects only catalogued error codes. No mutation is automatically retried.

The manager clears its private metadata on failure, unmount, profile change and
connection-change notification. Explicit reload reconciles uncertain outcomes.
A successful mutation broadcasts invalidation without identity or credentials;
late results cannot replace a newer local request. The server independently
revalidates session and resource generation before response release.

The overlay installer registers `/settings/github` and an authenticated Settings
entry only when the deployment capability is enabled. Normal previews retain
their existing settings. OAuth returns navigate to this fixed manager; code and
state are not forwarded. App registration remains a human action; local setup
never creates or changes a GitHub App. Source-read consent grants no Agent or
write permission. Private Skill browsing is a separate access boundary.

All controls require browser validation and independent review before delivery.

The connection screen leads with Connect GitHub and repository selection. Advanced
contains one-time GitHub App setup, callback details and optional token entry.
Missing setup opens that disclosure explicitly; credentials remain transient.
