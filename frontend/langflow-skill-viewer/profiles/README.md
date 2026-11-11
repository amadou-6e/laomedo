# Local profile entry

`ProfileEntryGate` selects the profile UI only when the backend explicitly enables
it. The existing login/signup remain available unchanged in ordinary previews.
`ProfileEntry` owns picker, creation, PIN entry and uncertain-result states from
the canonical local-profiles Draw.io. `api.ts` calls existing upstream login and
checks the authenticated identity before restoring the cookie session in a fresh
document. This discards old query/mutation/store callbacks on profile entry. It does
not store PINs, mint tokens or introduce another authentication protocol.

Failures use the shared catalogue and ErrorExplanation. Unknown save outcomes
require checking the list; they never automatically retry creation. A forgotten
PIN blocks that profile; the first release has no PIN recovery or deletion.
Private-session revocation remains a dependency on #259 before private access.

The overlay is source code, not evidence that the real user stories work. Build,
unit checks, real browser paths and final owner inspection remain separate gates.

Tabs in one browser context share a cookie session. `ProfileSessionSync` announces
confirmed context changes without credentials and replaces other documents so
old requests cannot populate a new profile's stores. Independent simultaneous
profiles require separate browser contexts. Actual cross-tab behavior remains
unverified until the real browser stories pass.

The pinned upstream fetch interceptor mutates request headers. Every profile API
request supplies a mutable header record, including GETs. The owned header tests
cover that browser-observed contract and project session data to safe identity.
Entry cards use a viewport-bound scroll container because the native canvas page
has a larger minimum width; that canvas constraint must not clip profile forms.

`ProfileIdentityMutationGate` uses the existing native password-form seam and
wraps the profile-picture editor. Profile mode does not offer identity mutation
controls that its backend refuses; ordinary preview mode retains those editors.
A failed capability check never exposes a blocked editor.

Profile name buttons opt out of the native Button's title-case conversion so
the picker preserves the exact stored name. The sign-out notice offers an
accessible Close control during waiting and failure; closing dismisses the
notice only and never claims to cancel a request or confirm sign-out.

Picker rows include a decorative UserRound icon beside each profile name. ProfileEntry clears local validation feedback when its fields change and clears previous-screen errors on picker navigation. Shared catalogue copy uses plain entry guidance; uncertain save and sign-out outcomes retain their recovery paths.

Picker rows use fixed initials avatars, left-aligned names and chevrons; a divider separates the secondary Create profile action. Field-specific catalogue errors use aria-invalid/aria-describedby. Authentication and uncertain-outcome recovery are unchanged.

The PIN-entry screen uses Log in and a heading-level back arrow labelled Back to profiles; the existing back handler clears PINs and pending requests still disable navigation.
