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

`ModelSelection.tsx` owns the compact composer control: a single model/effort
trigger opens model radio choices and a discrete annotated effort slider in a popover. Selecting values changes only
the next submission; it never submits a prompt. The composer shares one rounded
surface with its footer controls. History collapses from its full-height edge;
new conversation sits at the sidebar bottom. Tool names themselves expand their
retained input/output, with original Activity row styling and smaller type.
User and assistant message bodies share the same small text size. Double-clicking
the conversation heading edits its title; keyboard activation also opens editing.
Enter saves through the owner-scoped rename endpoint and Escape cancels.

Session feedback calls for a visual selection experience: the empty chat shows a
workflow illustration and a provider card with the existing OpenAI brand asset.
The composer picker displays discovered models as selectable logo cards, keeping
native radio keyboard behavior and the effort slider. Only the supported Codex
assistant provider is shown; these cards do not imply new provider integrations.

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
