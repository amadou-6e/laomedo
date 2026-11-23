# Application assistant

Claude `/usage` renders, copies and exports only the native Limits section,
including its reported percentages, reset times and bars. Missing limits show
an unavailable message; the full native receipt stays retained by the runner.

`NativeCommandMenu` refreshes the observed catalog when its provider, run,
thread or active-turn state changes. Aborted older reads cannot replace the
current result. Fetch errors expose Retry even when app-owned commands exist;
catalog reads never invoke a command or a model.

`ModelSelection.tsx` keeps native model radio controls over their full visible
rows with transparent styling. Pointer automation and keyboard selection use
the same control without changing the row's appearance or dispatching a turn.
`MessageRow.errorShownAbove` suppresses only an identical explanation already
shown in the conversation recovery banner; distinct historical errors remain.

## App-owned commands

`commandPreviews.ts` distinguishes application actions from native commands.
Codex `/logout`, Claude `/login` and `/logout`, and OpenCode `/connect` open
Settings → Providers without disconnecting an account. Codex and Claude `/rename`
open the existing conversation title form; Save/Enter uses the existing PATCH
route, and Escape cancels. These actions never invoke a native tool or model.
Plan mode and goals remain deferred; repository reviews remain unavailable in
the scratch workspace. Their menu entries stay disabled with explicit reasons.

## Account selection and composer admission

`AccountSelection.tsx` owns the compact composer account menu: provider icon,
short account label, highlighted selected row and a separated Manage accounts
link. Its popover handles outside-click/Escape dismissal; arrow keys move among
account choices. New chats default to the first connected, ready account returned
for the current profile and provider. If none is ready, a connected account whose
access token expired can be selected for the existing model-discovery and host
refresh path; revoked, reauthorization-required and unavailable accounts are not
automatic defaults except OpenCode's `opencode_go_key` local-custody summary:
its `unavailable` means upstream authentication has not been verified, not a runner
outage. It is eligible for default selection, with normal admission unchanged.
Users can change the choice before starting chat;
selection never creates a session or sends a prompt. Existing conversations keep
their exact saved account and generation. Other providers are never fallbacks.
`ProviderIcon.tsx` shares the existing provider brand assets between that menu
and the welcome cards. Welcome cards have a 320px maximum width, shrink with the
sidebar, and align their icon/text columns. The explanatory sentence keeps its
independent width.

`AssistantPage.tsx` uses the draft placeholder for missing account admission:
Select an account, or No account available. The account trigger repeats that
state without an extra selection paragraph. Account/model loading and empty
model discovery remain explicit. Missing selection disables model selection and
Send without showing a stale model or effort; drafts remain editable. Switching
providers preserves the draft and defaults only within the newly chosen provider.
The composer remains editable during startup, dispatch and active responses.
Send remains fenced until the current operation settles; typing does not queue
or submit another operation. Late acknowledgements preserve a newer draft.
Connect account and Manage accounts navigate to `/settings/providers` in the
current tab; they do not depend on popup/new-window handling in VS Code.
Before leaving, retain unsent drafts and the selected provider in profile-scoped
tab session storage and restore them once on return. Profile changes/locks clear
retained drafts. Storage failure asks before discarding work. Document navigation
also preserves the graph editor's existing `beforeunload` unsaved/build guard.
The empty slash menu distinguishes starting a native session from an unavailable
or filtered catalog. The menu displays the complete observed catalog, including
unavailable commands with an explicit disabled state; observation never grants
execution. `commandPreviews.ts` lists the pinned Codex adapter's eleven built-ins
and initial known Claude/OpenCode entries as documentation previews, never a
complete native observation. Unavailable native handlers remain unfinished work.
Only initial Codex `/status` is selectable; other previews require both actual
session advertisement and implemented admission/settlement support. A preview
is never a native catalog or an execution grant. Menu-inserted trailing whitespace still dispatches
initial status as the exact non-model operation.

An incomplete or unmatched slash prefix sends as ordinary chat. An exact observed
unsupported command or invalid arguments is refused before effects. Editing or
selecting another command dismisses only definite command-input rejections;
uncertain dispatch, account, model and observation errors stay fenced. This
prevents an earlier input error from permanently disabling Send.
The reserved names in `providerCommandNames` include all eleven pinned Codex
built-ins, known Claude built-in names, and OpenCode init/review/compact. Reserved
names do not imply native availability; terminal-only names refuse rather than
fall through to an ordinary prompt. The advertised catalog is authoritative once
the session exists.
These names refuse when unadvertised, as do exact observed unsupported entries;
the list grants no execution capability. Ordinary text stays inside the
assistant instruction prefix, outside adapters' leading-slash command parsing.

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
Ordinary message bubbles hug their text and padding, remain right-aligned, and
wrap within the existing maximum width for long or multiline content.

Model discovery has its own loading state: switching conversations never locks
the draft editor while model discovery or history is loading. Sending still waits
for the selected conversation, available models and execution admission. Native
approval cards align to the right; their white Approve button is the primary action.

`NativeCommandMenu.tsx` reads the selected session's observed command catalog when
the user types `/`, filters discovered entries, and inserts the chosen command.
Matching commands precede matching skills, with usable entries first within each
group. Headings and the divider appear only when both groups have matches.
Blocked entries show a concise capability reason; their full explanation remains
in the title and accessible description. Filtering never grants execution.
The menu floats above the composer without resizing it. Compact single-line rows
pair a command icon/name with a muted, ellipsized native description; the full
description remains available in the button title and accessible content.
Arrow Down moves from the composer into the menu; arrows navigate, Enter selects,
and Escape closes it. A session without an observed catalog gets an explanation
and, for Codex, the non-authoritative startup previews described above. Exact
observed commands use the human native-command route; they never fall back to
ordinary prose after refused or uncertain dispatch. Unmatched slash text is chat.
Completed native controls are classified by provider and command name. Their
retained output is rendered and copied directly, without model Activity lanes,
earlier token usage or a partial-model-reply warning. Completed command receipts
are not rendered as duplicate cards; the command message and its retained result
remain visible. Pending approvals and non-success outcomes remain visible. A native
report may describe an upstream error without establishing service health.

Sending an explicitly selected native command or skill is the human approval of
that exact invocation. Assistant-proposed invocations still require a decision.

Chat reads the signed-in profile from the application AuthContext, which the
HttpOnly-cookie session probe updates. It does not read the separate Zustand
userData slot: normal profile login does not populate that slot. Profile changes
fence the retained chat state and reload the account list.

Normal profile access-token renewal keeps the provider boundary's verified
canonical browser lease. Assistant admission, approval cards and logout use that
same identity rather than treating each renewed access JWT as a different app
session. Only a verified renewal alias may extend the retained session deadline;
explicit revocation and owner mismatches always win. Unrelated logins do not
inherit old pending approvals. Pre-fix cards require a fresh proposal; this does
not migrate or rebind them. Verified fingerprint aliases are retained with the
assistant session fence so restart cannot undo a logout. No bearer is stored.

NativeUsage renders verified Claude limits in the same muted, rounded card chrome as NativeStatus, with Close/Show limits controls. It does not alter retained output or approval policy.

NativeCommandMenu groups provider-reported skill rows under Skills, independently of Laomedo registry skills. Unsupported skills display capability-specific reasons without granting invocation.

An idle, observed conversation remains sendable after a definite request refusal;
displaying a previous request error does not itself block the next message. Active
attempts, uncertain pending submissions, observation errors, connection identity
and attention states retain their existing admission fences. Enter in an open
command picker selects its first usable match; a subsequent Enter sends after
selection, while Shift Enter inserts a newline.

Conversation history replaces its provider text markers with monochrome SVG
marks in the metadata row. Faint rules separate vertically stacked conversation
rows; metadata does not have an extra internal divider. History uses loading
on scroll instead of a pagination button. Active conversations have a spinner;
background work replaces the static switching tip. The assistant sidebar shares
one arrow rail for drag resizing and click collapse, with drag movement suppressing
collapse. Model labels omit the OpenCode Go prefix while retaining exact IDs at
the selection, accessibility and provider boundaries.
The Claude monochrome mark reuses the pinned upstream vector without its colored
background tile; provider names remain available to screen readers.
