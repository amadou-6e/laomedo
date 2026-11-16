# Application assistant

Normal provider-backed chat, with no assistant workflow. The approved geometry
and states are A1/A2 in specs PR424's application-assistant.drawio.

Owner feedback updates the layout: collapsible history with a plus action, a
chat-first empty state with provider selection, and per-turn model/effort controls
beside the composer. Consecutive tool calls share a card with per-call timing;
technical call IDs and repeated Assistant labels are omitted. `ToolCalls.tsx`
owns this assistant-specific presentation without changing graph Activity views.
The authenticated application Activity response supplies fixed authoring-tool
display names derived from the forwarding layer's canonical alias rule; it adds
no capability and leaves common Activity payloads and retained snapshots unchanged.

`models.ts` owns wire types. `api.ts` makes one same-origin request without
automatic inference replay or authentication-refresh retry. `AssistantPage.tsx`
owns conversation selection, model binding and composer state. `Message.tsx`
renders existing normalized Activity and authoritative receipt cards; native
user-prompt wrappers are hidden in favour of the actual retained user message.
`AssistantEntry.tsx` adds the header's explicit new-tab action and background
activity indicator. The pinned installer mounts `/assistant` under the ordinary
authenticated application wrapper and fences the existing sign-out action.

Selection/reopening/polling never sends a model prompt. Each submitted message
retains one client key across a lost response. Unknown submissions reconcile;
they do not automatically receive a new key. The tab's owner-scoped session
storage retains that original key and text across reload. An explicit Retry
same submission action reuses it; accepted submissions return their existing
reservation without native dispatch. Lock and profile changes clear that local
pending state. Unavailable session storage refuses before submitting a prompt.
Profile changes discard private
rendered state and reject stale responses. Draft links come only from database
receipts, open a new tab after a click, and preserve the original editor.
