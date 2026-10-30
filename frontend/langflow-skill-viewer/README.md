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
selected ID/revision and clears old data while loading. Opening, browsing or closing never executes the graph or changes a
skill revision. Other component nodes keep the existing Code action.

## Skill source keyboard boundary

The `Source` component owns keyboard isolation for its read-only Monaco host.
Monaco must handle editing prevention, selection, navigation and Find first;
non-Escape keydown and keyup events must then stop before canvas shortcuts.
Escape keeps the existing Find-first, dialog-second dismissal behavior.
This boundary also covers Monaco's native EditContext DIV, which is not an HTML
form field and therefore bypasses the canvas hotkeys' form-tag exclusion.

The actual Edge run of candidate `67177b1` exposed this failure: clicking inside
the editor and typing printable text closed Skill files and opened Assistant.
The editor and registry bytes remained unchanged, but keyboard isolation failed.
This is a product failure, not a passing read-only demonstration. A source correction alone does not establish verification. Record the exact
revision, frontend/browser evidence and focused review separately; the earlier
`67177b1` assets do not contain the correction.

Observable acceptance: printable keys remain in the open read-only viewer without
opening Assistant or invoking graph actions; source and registry bytes do not
change. Keyboard selection/navigation and Find still work. Escape closes Find
before closing the viewer. Internal native-EditContext/event tests support this
contract but do not replace the actual Edge recheck or owner validation.

## Canvas lifetime during background reads

`PageComponent` gates its initial canvas on the builds query's `isLoading`, named
`isBuildsLoading` locally. A cached builds refresh can have `isFetching=true`
without initial loading: it must preserve the mounted ReactFlow tree, node
selection and open viewer. The pinned query library defines initial loading as
pending and actively fetching; an initially paused request or completed error
keeps the former non-fetching gate behavior. No global viewer store is introduced.

On reconnect, the existing Reload files/history controls remain in the same
viewer and repeat only their read. Background build monitoring must not dismiss
it. `7492045` exposed the old `isFetching` gate unmounting the canvas before a
response returned; record corrected behavior with exact-source browser evidence
separately. The focused `tests/browser/canvas_refresh.cjs <loopback-flow-url>
<skill-node-id>` regression holds a real builds response in transit to check the
same mounted child during refresh. Its controlled interception is supporting
coverage, not a replacement for the complete real no-interception recovery path.

Cancellation retires the client's interest and ignores results for a closed or
changed selection. It does not guarantee that a server read stops or that the
browser emits a network-aborted event; an already-issued read can finish.

## Skill inspection failures

The existing file-view dialog renders failures as inline viewer content,
through the shared `describeNodeFailure` catalogue and reusable `ErrorExplanation`
body/copy formatter. It will not mount a notification portal, add another modal,
change notification placement/focus, or offer runner/graph/model/write actions.
`ErrorExplanation` names the shared descriptive body; `formatErrorCopy` formats
only that presenter's safe title, explanation, recovery and allowlisted technical
details. Existing `CopyIcon` supplies the subtle copy affordance. Shared code
lives under `components/laomedoErrors`; viewer code depends on that boundary.

| User story | Observable acceptance criterion |
| --- | --- |
| Open the selected/current revision when inspection fails | Show a plain-language title, explanation and truthful recovery inline; retain the stable code under Technical details; no raw response/payload/trace appears. |
| Load history or a previous revision when its read fails | Show the same shared explanation in the affected pane; a history failure leaves current files usable and a failed comparison does not show stale files. |
| Choose a missing, mutable, unsafe or oversized revision | Explain selecting an immutable/available/safe revision or the viewer limit; no blanket Retry or Reload control claims to repair an immutable refusal. |
| Read fails for an unrecognized external reason | Use a neutral inspection-specific safe fallback with cause unconfirmed; expose only allowlisted diagnostics. Read-only Reload files/history may repeat the same GET, without operation/model rerun. |
| Change selection or close while a request is pending | Cancel client observation of the old request; late success/failure cannot overwrite the current selection or reopen dismissed content. |
| Copy a failure | Existing subtle icon copies the shared safe explanation and technical details, never arbitrary backend bodies or traces; manual text selection remains available if clipboard access fails. |

`Reload files` and `Reload history` refer only to repeating the read of the same
selection. Known immutable/unsafe/oversized/invalid refusals have no reload
button. Selecting another revision remains an existing node/dialog navigation
action. No automatic request replay, editing, graph execution or model call is
introduced. Summary-source and invalid-operation codes have catalogue
entries based on their actual pre-publication/proposal effects. `describeInspectionFailure`
reads only the public response code and delegates to the shared presenter. Unknown
codes retain safe diagnostics but use the neutral read-only viewer explanation.
The shared code filter rejects unknown credential-prefixed values (`sk_`,
`gh[pousr]_`, `github_pat_`, case-insensitively) before rendering or copying them.
Exact catalogue codes and admitted native timeout codes retain priority; ordinary
safe unknown machine codes remain inspectable. Internal prefix-only sentinels
exercise shared text/structured errors and the viewer's DOM/copy boundary.
Comparison read failures use the comparison-specific fallback, including when
the response has no code or an unknown safe code. Its recovery refers to the
existing Current source/history controls; Reload files repeats only that
historical revision read. Copied explanations retain this comparison context.
The decoder accepts only the declared public `response.data.code` and existing
`response.data.detail.code` slots. Installed Langflow's 404 handler unwraps the
detail object into the first shape; standalone FastAPI retains the second.
The real `67177b1` missing-revision check exposed that the first shape previously
lost its known refusal and offered a futile reload. Both shapes must preserve
known refusal codes and the shared unknown-code/redaction policy without echoing
response text or changing the HTTP payload. Record browser verification against
the exact installed revision and frontend assets separately from this contract.
Node identifiers use the same credential-prefix exclusion as unknown codes,
before they can appear in Technical details or copied explanations. This does
not change the deliberate safe unknown-code policy described above.
Edit-attribution and missing-agent-provenance codes also have descriptive entries;
no admission or operation behavior changes. Existing operation HTTP wrappers
still collapse refused proposals to `skill_operation_refused`; catalogue coverage
does not claim that those wrappers expose the original inner code.

Frontend/catalogue tests are internal controls only. Full real-browser normal,
failure, stale-selection, copy, focus and read-only paths on the final installed
app require revision-bound browser evidence and user validation recorded
separately; internal fixtures do not establish acceptance.

The optional `laomedo.integrations.langflow.viewer:create_app` backend factory registers
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

The host source service is `python -m laomedo.skills.interface.sources.cli`: configure its
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

OpenCode agent nodes use the same Activity entry point. Provider-qualified message snapshots, capture limits and usage semantics are documented in [the OpenCode node guide](../../examples/opencode-node/README.md).

The runtime diagnostic change updates four existing error entries only:
`opencode_controller_startup_failed`, `opencode_container_cleanup_unverified`,
`lease_service_unavailable`, and `lease_service_lost`. They describe observed
startup, owned-resource cleanup and supervision uncertainty without assuming a
controller API exited, inventing a separate operator, or offering a blind retry.
The original cause of the observed startup failures remains unknown. Private
attempt diagnostics do not add public response fields or a new viewing control.
The remaining 99 baseline entries mentioning an operator are a follow-up wording
and coverage gap; the targeted regression guard does not certify the catalogue
as a whole. Browser presentation and real recovery require separate validation.
