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

Account rows and details use the Codex mark, matching the installed OpenAI Codex
extension asset `codex-d905da579253.svg` (26.1007.21434), rendered in the theme
foreground colour. Details identify reauthentication as Sign in to Codex again;
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
