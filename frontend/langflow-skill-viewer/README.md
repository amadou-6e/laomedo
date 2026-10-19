# Langflow Skill files overlay

## Agent activity appearance and node names

The graph selector lists captured executions of the current graph. Labelled
rules separate Graph run timeline and Selected agent run. Invocation metadata
uses plain labelled values; usage and diagnostic evidence precede Conversation.
Conversation uses the selected open-section style, right-aligned user messages,
left-aligned agent messages and safe Markdown (no raw HTML or remote images).
Its keyboard-focusable body scrolls independently at a maximum height of
`min(360px, 60vh)`; the heading stays outside that scroll area. Short threads
size to their content. No automatic scroll or model execution occurs on viewing.
Tool calls use compact utility rows with exact commands and native read-action
names when available. Output and raw metadata start collapsed; unknown tool
payloads remain inspectable. A small source icon at the right of each message
opens its exact source in a bounded popover, without an extra disclosure row. Child-thread messages use
a distinct Subagent label with a short native thread ID (full ID on hover);
subagent start/completion rows use observed native kind and path. Evidence warnings and
capture limits remain visible. This is a display change, not new trace capture.


The Agents tab uses Langflow's existing buttons, status badges and JSON code
viewer, with compact trace-style headers, rows and metric cards. Its ChartGantt
navigation icon is distinct from Traces' Activity icon. All existing activity
details, timeline lanes, usage and evidence warnings remain available.

To name an agent, select its canvas node, choose the pencil (Edit node details),
edit the title, and save. Capture records that visible title at invocation start;
later renames do not rewrite recorded names. Older invocations with no recorded
title use the current canvas title, falling back to the node ID if unavailable.
Node identity details disclose that fallback and retain the stable routing ID.

Tracking: Laomedo #154, specs #370. This is a small frontend overlay for upstream
Langflow v1.12.3, commit `fec71dca901949c09ed4d63315804337cd2eb13d`.
It is not an upstream plugin API or a vendored Langflow distribution.

Apply `python tools/apply_langflow_skill_viewer.py <upstream-checkout>` in a clean
checkout of that exact revision. Use Node >=20.19 (tested with Node 22), then
`npm ci` and `npm run build` under upstream `src/frontend`. The overlay pins
Monaco 0.57.0 in the upstream package and lock file. It reuses Langflow's React,
Markdown and dialog packages. Monaco and workers are bundled locally, without
a CDN. Retain [Monaco's MIT license](MONACO-LICENSE.txt) with distributed builds;
the upstream Langflow license also applies to its patched files.

The selected LaomedoSkill node exposes Skill files instead of primary Code.
A read-only Monaco viewer includes nested folder navigation, open-file tabs,
source search, Markdown preview and binary metadata. The panel snapshots the
selected ID/revision, clears old data while loading, and handles fixed errors
with Retry. Opening, browsing or closing never executes the graph or changes a
skill revision. Other component nodes keep the existing Code action.

The optional `laomedo.langflow_skill_viewer:create_app` backend factory registers
GET `/api/v1/laomedo/skills/{id}/{sha256-revision}` before the SPA catch-all,
using the installed Langflow authentication dependency. Configure
`LAOMEDO_SKILL_STORE` to a read-only registry mount and `LANGFLOW_FRONTEND_PATH`
to the built overlay. No provider/runner credentials are read by this route.
The core Laomedo package does not gain a mandatory Langflow/FastAPI dependency.

API tests: `python -m unittest discover -s tests -p test_skill_inspection.py`.
Run them in the pinned Langflow image for the optional HTTP/auth and Linux link
checks. Browser regression: `NODE_PATH=<Playwright installation> node
 tests/browser/skill_files.cjs <fixture-manifest.json>`. The manifest identifies
a disposable loopback test flow containing two Skill nodes with distinct immutable fixture revisions and a non-agent control node,
and no agent/publisher or credential binding. Include `second_skill_id` and
`second_revision` in the manifest for the delayed selection-change check. No model turn is needed.

Activation is separately gated. See [deployment draft](DEPLOYMENT.md). The
existing application server, graph, database and runner remain unchanged until
that concrete configuration is approved.

## GitHub PR alignment

LaomedoGitHubPR uses the Issue node's selector clearing and stale-response guards.
Its primary toolbar actions are PR viewer and Open in GitHub. PRViewerModal reads
the exact configured repository/number through authenticated POST
`/api/v1/laomedo/github-prs/inspect`, with no operation payload or model call.
It displays current PR metadata, branch pair and safe Markdown. A runtime-only
reference without picker selection does not become a saved selection.

Copy PRViewerModal.test.tsx beside the applied PR modal as index.tsx's sibling
and run the upstream Jest suite for that file. The tests unmock Markdown so they
exercise real rendering. The local evidence is recorded with source hashes in
`examples/github-pr/evidence.json`. The full production build and five viewer
tests passed; isolated Edge rendering exercised the real dialog. This does not
claim an installed full-app selector test or active GitHub PR service deployment.

## Recorded verification

On 2026-10-12, the pinned Langflow image passed all ten file and authenticated
HTTP tests. The actual imported fixture flow passed the Edge browser regression:
Skill action, ordinary Code action, read-only source, search/Escape, safe preview,
nested files, tabs, binary metadata, immediate Retry, delayed second-revision
loading, unchanged saved graph and no execution requests. No model turns or
GitHub publication writes were used. The host suite passed 675 tests (14 skips)
before the final depth-only testcase, which passed in the ten-test image run.
The Node 22 frontend build and clean-checkout overlay application passed.
Whole-upstream TypeScript checking fails with 253 existing diagnostics; the
overlay comparison added zero diagnostics. This is not a claim that upstream
type checking is clean.

## Linked-source selector (#157)

The same overlay adds searchable Skill and Revision dropdowns for an optional
Source. Source changes clear dependent choices immediately; late responses for a
superseded source/skill/revision are ignored. Discovery status is read-only.
Skill files accepts the resolved tuple only while it matches the current controls.
Source-empty old saved nodes retain their manual exact reference behavior.

The host source service is `python -m laomedo.skill_source_server`: configure its
registry, private state directory, allowed local roots and API token file. The
Langflow backend uses `LAOMEDO_SKILL_SOURCE_URL` and
`LAOMEDO_SKILL_SOURCE_TOKEN_FILE`. No transport token belongs in node fields.
Public GitHub/GitLab root URLs, allowed local folders and the existing registry
are supported; private Git authentication and GitLab subgroup URLs are deferred.
Existing local private checkouts can be supplied within an allowed root.

Run `tests/browser/skill_sources.cjs <fixture-manifest.json>` with Playwright.
The fixture must have a disposable source-only flow, two local skills, two local
alpha snapshots and a trusted Git fixture adapter offering main and tag v1.
It uses real custom-component refresh APIs and no model or publisher node.
Use a separate build output while a live viewer mounts upstream's default build.
See [source service activation draft](SOURCE-DEPLOYMENT.md).

## Agent node advanced controls

The pinned overlay also adds an inline Advanced controls disclosure to Codex and
OpenCode Agent nodes. It starts collapsed and preserves values when reopened.
Model, effort and the existing lifecycle Operation remain on the main form;
scalar technical controls move inside the disclosure. Hidden fields remain
hidden, wired inputs remain on the normal renderer, and other node types retain
the upstream behavior. No task/skill/output ports or execution semantics change.
The node geometry refreshes on disclosure/minimize changes. Existing advanced
edit-dialog access is retained. The disclosure itself does not define model discovery; Codex model/effort options are loaded separately from the runner catalogue. It does not add a new session/execution-mode model. Test AgentAdvancedControls.test.tsx in the applied
RenderInputParameters directory; production browser checks use the existing real
Agent graph without a new model turn.

The original Codex agent node offers Activity in place of Code. It opens the graph Agents view with that node selected, choosing its newest captured graph execution and invocation. The timeline still shows the other agents in that execution. If the node has no capture in the selected execution, the view says so; viewing never starts a run.

The overlay applicator installs AgentActivityNavigation.ts at src/frontend/src/stores/agentActivityStore.ts. The node entry point uses an explicit transient target scoped to the graph, clears it when leaving Activity, and does not change canvas selection or save graph data. Opening Agents directly from the sidebar does not infer a target from selected canvas nodes.
