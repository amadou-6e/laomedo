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
