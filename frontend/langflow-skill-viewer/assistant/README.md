# Application assistant

## Graph editor sidebar (issue 296)

`AssistantSidebar.tsx` mounts the same `AssistantPage` on the editor's right.
`sidebarStore.ts` owns only the open/closed UI flag; conversations, inference and
approvals still use the existing owner-scoped assistant API. The sidebar owns its
conversation selection without changing the graph URL. It mounts lazily, then
stays mounted while hidden so closing it preserves its draft and active response.
The embedded conversation header is the sidebar top row: conversation title,
History, existing export/delete actions and full-window link. There is no extra
Assistant title row or header close icon. `AssistantSidebar` owns the 8px edge
strip that collapses the entire panel in chat, history and locked states while
retaining its mounted draft. `AssistantPage` owns the header History icon, which
opens or closes the embedded conversation list; the full-window history controls
keep their existing behavior. Expanded history keeps the full-window action
reachable, and the outer collapse strip stays available.
History starts collapsed in this narrow surface. The full-window router link opens the
selected saved conversation in the current tab.
The sidebar full-window icon leaves the editor in the current tab; unsent sidebar
text is discarded and the existing guard applies, including stopping an active
build. The divider hit area sits outside the panel so it does not obscure the
8px collapse strip. That outside 8px edge is reserved for resizing rather than
canvas pointer gestures. The divider supports dragging and arrow/Home/End keys. Width is bounded and
reclamped when the editor changes size. Narrow screens use an overlay, retaining
the mounted editor beneath it. Opening, closing and resizing never send inference.
`AssistantEntry` opens full-window chat in the current tab through the application
router, including the existing unsaved-editor navigation guard. Navigating away
while a graph build is running stops that build through the existing guard; use
the rail toggle to keep the graph running while opening chat beside it.
`AssistantSidebarToggle` is an icon in the graph left rail. It toggles the right
sidebar without changing the selected left section, graph URL or canvas. Closing
the panel returns focus to that rail control. Existing graph tools and human approval rules remain unchanged.

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
The composer retains its compact model list and effort slider; logo cards apply
only to the provider choice, not to model selection. Only the supported Codex
assistant provider is shown. New chats visibly reuse a supported current/recent
model and effort, falling back to the first discovered model with a supported
effort. This is a composer selection, not a claim about the provider's defaults.
It never submits inference; opening an existing conversation keeps its binding.

`Thinking.tsx` renders the shared accessible waiting status; `Thinking.css` gives
its letters a subtle staggered lift and respects reduced-motion preferences.
`UserMessage` in `Message.tsx` renders both optimistic and retained user bubbles
with identical geometry. A normal send shows the bubble and Thinking while its
acknowledgement/history arrives. Retry guidance appears only for uncertain or
restored unobserved submissions; it keeps the original idempotency key.

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

The composer sends on Enter, preserves Shift+Enter for newlines and ignores Enter during IME composition. Thinking is visible only before answer text appears, including streamed activity or a retained response.

GraphActions.tsx renders server-built graph edit/run previews and human-only approval decisions. It never dispatches inference or approvals on render; unknown/stale/expired outcomes remain explicit. Wire records stay in models.ts.

Approval cards foreground Rename/Edit/Run and a short description; technical identities remain in backend receipts. Agent prose must not duplicate cards.

Settled approval cards collapse to operation, muted change description and a short
outcome. GraphActions uses a top-right ExternalLink icon with an accessible name;
no technical Details section or separate success sentence is rendered. Pending
controls and conversation consent scope remain explicit. Failure/unknown outcome
labels retain their recovery meaning in tooltips.

Run cards use a human-readable sentence with the actual server-preview input,
not the model summary: Run/Running/Ran workflow "name" with input "value".
Only a successful result uses Ran. Outcomes occupy their own left-aligned line
below the description; they never share the graph icon's right-hand column.

Rename cards follow the same sentence layout as runs, without a separate title:
Rename/Renamed workflow "old" to "new", followed by the left-aligned outcome.

Edit uses that same single-sentence layout: Edit/Edited workflow "name": brief
change description. All three categories share typography, icon and outcome layout.

`transcript.ts` collects all retained message pages and normalized answer text for
a Markdown snapshot; it excludes native/tool payloads, marks incomplete retention
and never dispatches inference. The header export ignores results after selection
or owner changes. `CopyAnswer.tsx` copies the complete retained agent response since its user request,
with local success/failure feedback. The message container uses compact bottom
padding so answer controls remain close to the composer. UI geometry and these
transitions are specified in application-assistant.drawio A3 TRANSCRIPT-01.

`responseTranscript.ts` assembles one request-scoped response:
assistant text and displayed tool/command inputs/outputs in retained activity
order, followed by graph action receipts, saved drafts and incomplete/active state. It excludes the user/native
prompt wrapper and other requests. `toolCall.ts` owns shared display-field/name
selection for ToolCalls and copying; raw native records are not serialized. One
Copy control sits below the full response and copies a current streaming snapshot.
Conversation export remains the separate text-only Markdown snapshot.

`DeleteConversation.tsx` owns the header trash control and named confirmation:
Cancel preserves the chat; Delete calls the owner-scoped endpoint once, reports
failure locally, then asks AssistantPage to clear only that chat's local state
and return to a new conversation. Saved workflows stay; active chat/graph work
blocks deletion. Selection/owner changes discard late results. A3 DELETE-01
defines the confirmation and outcomes.

Workflow-card links use the application router to open the corresponding graph
in the current tab; integrated-browser popup handling is not required.
Opening a different graph resets the sidebar's selected conversation; saved chats
remain in History. Opening the current graph reloads its saved state, closes the
sidebar and discards unsent sidebar text. The editor's existing browser leave
confirmation protects unsaved graph changes and active builds.

`NativeActions.tsx` renders exact built-in command/argument proposals with Approve
and Reject, followed by compact authoritative outcomes. It uses only human app
routes and never submits an assistant prompt itself. `NativeAction` wire types
stay in models.ts. Command messages reuse MessageRow/Copy; responseTranscript
includes native proposal receipts. No additional conversation surface is created.


# Assistant rendering

`Message.tsx` assembles retained activity and responses. `NativeStatus.tsx` renders
an approved native `/status` response as a compact, dismissible monospaced panel.
`statusFields.ts` extracts only fields actually reported in that response; absent
context or quota data remains unavailable, never inferred from a different session.
The chat ID and native thread ID are separately labelled.

`toolCall.ts` names retained native items, including context compaction.
`ToolCalls.tsx` displays their observed outcome even when no textual result exists.
Copy/export continue to preserve the original native response.
Executed native command messages are plain right-aligned text, without the normal
user-message bubble. Ordinary user messages retain their existing appearance.

Model discovery has its own loading state: switching conversations never locks
the draft editor while model discovery or history is loading. Sending still waits
for the selected conversation, available models and execution admission. Native
approval cards align to the right; their white Approve button is the primary action.
