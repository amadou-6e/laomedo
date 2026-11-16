# Provider connections Settings

`ProviderConnections.tsx` owns the approved list, provider choice, Codex method,
pending, details and recovery screens. `api.ts` owns validated wire projections
and bounded same-origin browser calls. `providers.css` uses application theme
tokens and the GitHub connection card/footer language. Back and Refresh remain
icon buttons below the card. Refresh never starts authentication.

The initial route is app-owned Sign in with ChatGPT for Codex. Other provider
types are visible but unavailable; no ambient-login or API-billing fallback is
offered. A pending opaque attempt ID may survive same-tab native navigation;
OAuth state, URLs and credentials never enter browser storage. Native completion
returns to the original Settings origin. User-facing errors use the shared
catalogue. Disconnect and consumer binding require the matching host runtime
integration; do not present unavailable operations as working.
