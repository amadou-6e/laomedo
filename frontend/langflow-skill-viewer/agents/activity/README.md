# Agent activity

`GraphAgents` composes graph execution selection and the selected Agent run. Wire records belong to models.ts; pure projection, timing, filtering and export operations belong to utils.ts. Components render retained conversation, usage and telemetry. Viewing does not dispatch a model. `AgentActivity` is the native receipt modal; `AgentActivityNavigation` owns the app navigation store.

The main Activity scroll area ends with a muted MIT copyright footer, separated
from the conversation by generous spacing and followed by bottom padding.

An active invocation's main conversation shows "starting" until its first
turn is captured. Observed turn states and terminal invocation failures retain
their own status; an absent turn is not itself a failure.

## Search and counts

Each telemetry/conversation heading has an icon-only search toggle. Opening focuses
the field; closing/Escape clears hidden filters, Escape returns focus to the
icon, and Clear keeps the field open. Scope changes remount these components.
Empty telemetry is centered text without a bordered card. Major sections (selection and metadata, capture/partial
notices, usage, telemetry and conversation) are separated by 48 px (`gap-12`).
Counts show the total when unfiltered and matching of total while filtering;
conversation counts use "items" because they include messages and tool calls.
Capture, dispatch and export contracts are unchanged. The design reference is
ACT-295 in run-traces/design/agent-activity.drawio.

## Execution hierarchy

`GraphAgents` owns the selected graph execution and scoped activity. Its execution
container groups the selector, `ActivityTimeline` and selected detail panel.
`ActivityTimeline` renders observed conversation rows and nested selectable turns;
`onSelect` changes inspection scope only. Collapse controls hide descendants and
restore selection to the collapsed conversation if needed. Parent summary segments
retain idle gaps; only captured turn intervals are colored. `ProviderIcon` renders
monochrome provider marks with a neutral fallback for an unknown provider. Details
repeat the selected provider and a breadcrumb back to the full invocation.
All activity selects the invocation, so no conversation row is marked pressed
until its own conversation scope is selected.
The footer follows long content and rests at the viewport bottom for short content.

## Markdown verification

`MessageMarkdown` uses the pinned frontend's existing `remark-gfm` dependency for
tables and other GitHub-flavored Markdown. Raw HTML and remote images stay disabled;
tables scroll within the message when needed.

Run the activity suite from the patched pinned Langflow frontend with
`npm test -- --runInBand --config <implementation-checkout>/frontend/langflow-skill-viewer/agents/activity/jest.config.cjs --testMatch '**/GraphAgents.test.tsx'`.
The concern-owned config extends upstream's ESM allowlist for the real GFM parser;
the test explicitly disables upstream's GFM mock.

## Shared presentation ownership

`components.tsx` owns section search controls and their focus/clear contract,
status badges/dots, safe message Markdown and user-message bubble styling.
Activity and Assistant chat use the same message primitives; Assistant keeps
its existing no-links policy and plain-text user messages. Other feature
viewers and upstream rich-HTML chat retain their distinct content contracts.
`utils.ts` owns canonical status labels/tones and cycle-safe conversation
ancestry. `GraphAgents` derives conversation rows once and supplies them to
`ActivityTimeline`, whose keyed lifecycle owns only collapsed-row state.

`ACTIVITY_SCROLLBAR_CLASS` in `components.tsx` owns activity scroll surfaces: transparent tracks, theme-aware thumbs and no Chromium arrow buttons. Keep native scrolling and keyboard focus behavior. The same style covers timeline, Markdown table/code and tool-output scrolling; embedded upstream code editors retain their own scrollbar rendering. Only the bounded conversation/telemetry lists reserve a stable gutter.
