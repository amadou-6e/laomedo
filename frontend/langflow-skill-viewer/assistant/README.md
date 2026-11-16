# Application assistant

Normal provider-backed chat, with no assistant workflow. The approved geometry
and states are A1/A2 in specs PR424's application-assistant.drawio.

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
they do not automatically receive a new key. Profile changes discard private
rendered state and reject stale responses. Draft links come only from database
receipts, open a new tab after a click, and preserve the original editor.
