# Application assistant acceptance

Production implementation: `amadou-6e/laomedo` issue #282, draft PR #283.
This permanent `exp` concern owns disposable acceptance drivers. Production
tests must not import or fetch these files.

- `serve.py` starts a separate application database, private assistant workspace,
  ordinary native Docker profile and owned lease service. `--resume` retains the
  same state and origin for an explicit application-restart check. Opening the
  app submits no prompt. A private stop file requests graceful teardown.
- `check.py` signs into that isolated app and checks actual model discovery. Its
  native app session token is written only to private temporary runtime state.
- `turn.py` submits exactly one chosen user message and observes it. A stable
  client ID is never retried automatically. `--linked` explicitly creates a
  linked conversation; it does not rewrite or replay an uncertain predecessor.
- `stop.py` observes a native session before requesting exact-attempt Stop and
  then waits for settlement. Its polling bounds apply only to this experiment.
- `browser.mjs` uses installed Chrome in a fresh independent context, verifies
  the actual chat/card and explicit separate-tab editor, and retains screenshots
  locally. It never attaches to or exports the user's browser session.
- `verify.py` independently reads retained outcomes, canonical source-workflow
  revision, pre/post restart identities, native cleanup and browser observations.
- `selection.py` creates a separate acceptance conversation and submits three
  real turns with different model/effort choices, verifies recall, immutable
  message selections and native effective configuration, and requires the same
  native thread/run throughout. It never changes the presentation conversation.

Runtime pointers, database files, tokens, capability files, raw logs and browser
profiles remain outside this repository. They must never be committed. Only
sanitized conclusions and this harness belong here.

## Observed on 2026-11-16

Implementation head: `8460657ec0e2d41fb8b56c439e99107bd70da7b6`.
Base: `2344408faf24570581cc61498ec9796059d7baaa`.

The registered Codex image was built through shared acquisition, including its
embedded TypeScript/Vitest controls. Its immutable ID was
`sha256:a31dea3d18a56615562f9afe9cdd79341af8f77ea21e6c33949759c2d18d458a`.
It approves only the exact host-admitted MCP tool names, preserving the global
approval policy, sandbox and enabled-tool allowlist.

Real Codex used the actual six-tool Laomedo MCP server to save an ordinary
workflow draft. A follow-up recalled the draft. Active cancellation settled as
cancelled on the same thread, and a following message completed. A separate copy
was saved from an inspected workflow revision; an independent canonical revision
read confirmed the source remained unchanged.

After graceful application restart, the completed conversation resumed on the
same native thread and run, retained identical draft receipts, correctly recalled
the copy's name, and returned to idle. Native controller cleanup was confirmed and
resource cleanup verified. No workflow was run or published.

A fresh independent Chrome context verified the actual chat and receipt card,
opened its two-node workflow in a separate editor tab, and recorded no JavaScript
errors. The owner-shared VS Code integrated browser also showed the actual chat,
tool lanes and card. Screenshot files remain local because they contain browser
profile chrome; no session transfer was used.

Controls: 739 Agent cases passed with four skips, all 39 optional-runtime assistant
cases executed and passed, and all eight assistant UI cases passed. The production
frontend build passed. Both GitHub Work Graph and Python formatting workflows
passed for the exact implementation head. Full upstream TypeScript checking has
baseline failures; no assistant-file diagnostics were reported.

Earlier failed acceptance attempts remain recorded as uncertain. They exposed
native tool-admission and resumed-attempt ownership issues that were corrected;
they were not replayed or rewritten. A duplicate-name save returned an uncertain
outcome and created no authoritative card in that conversation. Model prose was
not treated as a save receipt. Later validation used an explicit linked
conversation and distinct draft name.

Claude reviewer session `62a1a754-1af6-477f-aa14-0b000a571381` completed
cumulative review of the full substantive diff from the base to the implementation
head above, including the refreshed screenshots. No High or Medium findings remain;
coverage is complete. Live evidence was supplied by the implementation agent, not
rerun by the reviewer. Low residual risks include bounded receipt/reconciliation
windows, activity rereads and some test gaps. No merge approval is claimed;
spec PR #424 is still an unmerged prerequisite.

## Owner feedback acceptance

The owner requested a chat-first empty state, per-turn model/effort selection,
collapsible history and grouped readable tool calls with timestamps/durations.
Real acceptance completed `gpt-6-luna/low`, `gpt-6-luna/medium`, then
`gpt-5.6-luna/low` in one conversation: all three completed on the same native
thread/run and recalled the marker. No workflow was run or published.
The retained application database restarted successfully with the new nullable
message selection fields, preserving earlier conversations and receipts.
740 Agent tests passed (four skips), 40 assistant tests passed, and ten UI tests
passed. Real protocol discovery also checks tool-display aliases against the six
actual MCP tools. Whole-upstream TypeScript checking retains baseline errors;
no assistant-file diagnostics were reported. Evidence and screenshots stay local.

Claude's cumulative feedback-delta review `8460657e` -> `4fb66109` is complete:
Implementation, Spec fit and Visual APPROVE. The confirmed generic-tool-label
finding V-M1 was corrected using the forwarding layer's canonical identity map
and rechecked against fresh real-data screenshots. No blocking findings remain;
the reviewer did not rerun the live probes. Spec PR424 remains unmerged and the
implementation PR283 stays draft; no merge is authorized by this evidence.

## Compact composer and follow-up styling

Revision `8918f8d8` applies owner notes 11–17 and the provided compact composer
reference. Browser acceptance now uses the real popover's native model/effort
radio labels, Escape, the sidebar edge away from its icon, bottom new-action
position, and tool-name expansion. Screenshots use dark mode at 1041×895 and
finish finite animations for stable capture; product animation is unchanged.
The ten UI tests and production frontend build pass, and TypeScript reports no
assistant-file diagnostics while upstream baseline errors remain. Exact-head CI
passes. Claude reviewed `4fb66109` -> `8918f8d8`, all six rendered states and the
full UI delta: Implementation, Visual and Spec fit APPROVE with no blockers.
The reviewer did not see the owner's reference bitmap, only its described
geometry and the actual implementation renders. No new inference was needed.

UI checkpoint0adee974: independent Chrome verifies the annotated effort slider with keyboard stepping, real conversation rename retained after reload with matching header/sidebar, and equal computed user/assistant font sizes (14px). The driver restores the original title, retains actual provider/MCP history and opens the draft separately (two nodes,one attached edge), with zero page errors. No inference submitted. Local screenshots/private runtime state are not committed. Native permissions were explicitly split into issue288 by the owner.

UI checkpointa15b9420: driver additionally asserts no Refresh models action and a rename input wider than70% of the header. Existing title persistence and draft/editor checks still pass; no inference submitted.

UI checkpointa3349105 adapts retained CoBrowse feedback with a workflow illustration and branded provider/model cards. Independent Chrome explicitly verifies model-card checked state, ArrowRight/ArrowLeft selection and focus returning to the selected card on reopen, alongside existing slider/title/history/editor checks. No inference submitted; screenshots stay local.

UI checkpointc2daa457 restores compact model list, removes provider caption and gives new chat a visible supported selection. Eleven UI controls and actual browser checks pass. hello.mjs submits one real greeting without opening the model picker; server202 accepted and same native message completed with a response. Initial observation hit an upstream fetch-wrapper headers requirement; corrected observation-only reattachment verified that same message without resubmission. Final response screenshot waits for actual message/prose content. The owner tab retains its unsent Hello. Private runtime identifiers/screenshots are not committed.
