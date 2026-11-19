# Provider connections Settings

`ProviderConnections.tsx` owns the approved list, provider choice, Codex method,
pending, details and recovery screens. `api.ts` owns validated wire projections
and bounded same-origin browser calls. `providers.css` uses application theme
tokens and provider-specific choices. `connections.css` mirrors the GitHub
connection Settings stylesheet from `feat/286` at `e7b0fa93`; the same `gc-*`
panel, heading, account row, detail and navigation classes are used directly.
Back and Refresh remain
icon buttons below the card. Refresh never starts authentication.

The initial route is app-owned Sign in with ChatGPT for Codex. Other provider
types are visible but unavailable; no ambient-login or API-billing fallback is
offered. A pending opaque attempt ID may survive same-tab native navigation;
OAuth state, URLs and credentials never enter browser storage. Native completion
returns to the original Settings origin. User-facing errors use the shared
catalogue. Disconnect and consumer binding require the matching host runtime
integration; do not present unavailable operations as working.

Account rows, provider choices and details use Langflow's existing OpenAI knot
logo for Codex, with white knot strokes and a transparent canvas and avatar
canvas, inside the same muted circular badge as other providers. The knot stays
white in dark mode and switches to dark in light mode to retain contrast. Saved Go-key
status uses normal foreground emphasis without claiming verified access.
Reauthentication starts directly from Sign in again. Adding another Go key
retains its originating connection so Back returns to those details. Claude's
code field appears only after the explicit Continue to Claude action; continuation
and completion buttons fit their text. Provider choices keep a centered group
with fixed logo and label columns, so logos align vertically across choices.
Details identify reauthentication as Sign in again;
account access and model usage are not inferred from successful authentication.

Connection details group compact reauthentication and Disconnect buttons together,
with reauthentication immediately before Disconnect and wrapping on narrow screens.

`SubscriptionAgents.tsx` composes per-harness tabs, graph-specific account
preferences and subscription-limit availability. Combined agent activity lives
in `GraphTraces` under Traces, alongside the existing flow execution view. Preferences persist through authenticated graph-owned routes; viewing
usage or changing selection never submits a model task.

Subscription allowances are distinct from run tokens and estimated cost. The
current ACP adapter has no account/rateLimits/read projection: show unavailable,
never infer remaining hourly/weekly/monthly allowances from run activity.

Graph settings follow GitHub Primer's plain, left-aligned settings sections:
headings with dividers, bounded form widths and consistent vertical spacing.
Subscription limits are a list with one row per connected account, independently
of the preferred account. Unsupported harnesses use a borderless empty state with a single greyed-out harness mark, without a cross-provider action; Codex without accounts offers Connect.
References: https://primer.style/product/getting-started/foundations/layout/
and https://primer.style/product/getting-started/foundations/typography/

Empty states center within the available content pane and show a muted harness
mark with static decorative Z lettering. OpenCode assets in `assets/` are from
https://opencode.ai/brand/files/opencode-logo-dark.svg and
https://opencode.ai/brand/files/opencode-logo-light.svg (retrieved 2026-11-18);
light/dark variants retain their original geometry and are displayed at 64x80.


OpenCode Go adds a masked subscription-key form with an accessible connection-name
field and a provider Console link. Keys are cleared after submission and Back,
never restored from browser storage. Saved keys explicitly lack verified upstream
identity/access. Exact repeated keys reuse the existing row; different keys cannot
prove different accounts. Per-harness graph preferences preserve other harness
selections and never route a Go key to a Codex or Claude node. Native Claude
connection support and real Go integration acceptance remain pending.

Claude Code uses the official client in an independent native volume. The pending
view opens its provider-owned link and relays one masked completion code back
to that same client. URLs and codes remain out of browser storage; code input is
cleared after submission. A lost submission response remains an uncertain outcome
and polling reconciles it rather than automatically submitting another code.
Real Claude sign-in/dispatch and independent final review remain pending.

The Settings list calls saved rows Accounts, including rows requiring sign-in.
The GitHub PR257 ConnectionAccounts and ConnectionNavigation layouts remain the
reference: preserve the card, identity/status row, explanatory copy, footer and
icon navigation. Connected accounts offer secondary reauthentication; native
accounts needing sign-in retain a primary recovery action. The Claude handoff
uses one instruction with the provider link and masked completion-code field.
Screen transitions reset ancestor scrolling; polling does not change scroll.
The Codex product icon is the unmodified codex-app-ga-logo-3e5209898ca3.png
shipped in OpenAI VS Code extension26.1007.21434, displayed without distortion.
