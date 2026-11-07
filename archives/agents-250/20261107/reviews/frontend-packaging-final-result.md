# PR250 frontend, Codex ACP extension and packaging (`02c2c291`)

These files keep connected ports and the saved model selection, open activity from the node toolbar, and show unknown usage as Unknown. The one exception is the zeros shown while a run is waiting for its first usage report (F-Q1). The Codex container extension forwards only an allowlisted set of native events, never credential, account or executor records. It adds no general command path to the network. Packaging, lockfile and CI hang together.

I found no confirmed defect: two low questions and two optional suggestions.

## What I read

- **`frontend-packaging-final-source.txt`, lines 1–2938 (the end of the file).** That covers:
  - **Agent activity:**
    - `AgentActivity` and its test;
    - the navigation store;
    - `components`, `conversation`, `GraphAgents` and its test;
    - `models`, the README, `telemetry`, `usage` and `utils`.
  - **Agent controls:** `AgentAdvancedControls` and its test, the `AgentModelSelection` test, the `ClaudeModelDropdown` test, the README, `RenderAgentInputParameters`.
  - **Integration:** `integration/agents.patch`.
  - **Codex ACP container:** `LaomedoExtension` and `LaomedoLaunch` with their tests, `native-events.patch`, the Dockerfile, README and `package.json`.
  - **Claude container:** the Dockerfile and `package.json`.
  - **Packaging and CI:** the CI workflow, the Claude README, `pyproject`, the `apply_langflow_skill_viewer` changes, `uv.lock`.
  - **Final test changes:** `test_langflow_local_auth` and the root-only history test.
  - **Claude `agent.py`:** lines 740–825 and 950–1045.
- **Not read:**
  - `SkillNodeControls`, `laomedoRecovery`, `claude-models.patch`, `claude-selection.patch` and `upstream.patch`;
  - the Codex upstream adapter outside the patch hunks;
  - `docker/claude/command_mcp.py`;
  - the frontend test runs and the build log.

## Questions to your four checks

**Control visibility and connected ports: kept**
- Only four scalar settings can move into the collapsed section.
- A connected field never collapses, and handles inside the advanced section are switched off (`RenderAgentInputParameters:156`).
- A connected Prior Run stays visible and hides again when disconnected. The tests check this through the real renderer.
- See F-Q2 for the legacy hidden fields.

**Saved model selection: kept**
- A model result that arrives after you picked something else, or after the runner URL changed, is discarded.
- An effort level the new model can't use is replaced; a valid one you edit mid-refresh is kept.
- Ordinary components keep their existing behaviour.
- An explicit refresh waits for the response and announces only a catalogue it actually applied.
- Native display labels are separate from the IDs that get submitted.

**Activity navigation: works**
- The node toolbar's Activity button sets a target and opens the Agents section.
- It picks the newest execution and invocation for that node.
- Opening Agents directly ignores whatever is selected on the canvas, and the target is cleared on unmount.
- The name recorded at run start survives a canvas rename.
- Loading runs, executions and details doesn't send any agent work.

**Unknown usage: shown as Unknown, apart from F-Q1**
- Null usage or cost shows as "Unknown".
- An unpriced observation never becomes zero, and no cost chart is drawn without priced data.
- Cumulative charts carry the latest value per thread forward and add threads once each.
- A turn or thread view without its own usage stays Unknown instead of borrowing the parent's numbers.
- A capture reason forces totals to Unknown.

## Codex container extension

- **Raw activity stays inside the allowlist:**
  - only `thread/started`, token-usage updates, `turn/*`, `error`, `item/*`, `turn/plan/*` and `turn/diff/*` are forwarded;
  - account, config and `environment/*` records are dropped, and a test checks this;
  - the executor bearer token goes only to `environment/add` and never appears in a forwarded notification;
  - all forwarded events are flushed before the prompt response, and a capture failure or missing root completion kills the native process.
- **No added command or network access:**
  - preflight is a fixed list of checks, allowed only before any session or prompt;
  - the `network` check is an outbound connect attempt that's expected to fail;
  - `item/tool/call` serves only `laomedo_output_precheck`;
  - native launch arguments must alternate between `-c`, `--enable` or `--disable` and a value, are passed without a shell, and fail closed;
  - the session root is explicitly untrusted, and `/draft` and the absence of MCP servers are enforced;
  - slash commands are switched off when the extension is active.
- **Build:** the Dockerfile pins the base image digest, the upstream commit and archive checksum, and the Codex lockfile. It runs typecheck and the tests before building, and records checksums.

## Packaging and CI

- **Dependencies:** the `runner` extra adds pinned `agent-client-protocol==0.12.1` and `pywin32` on Windows. The latter matches the private-state Windows security code. `uv.lock` agrees with `pyproject`.
- **Package data** now points at the new owners (`host.mediation`, `agents.agents.codex`).
- **Overlay installer:** it copies from the new `agents/` and `integration/` folders and writes a `graphAgents/index.tsx` that only re-exports `GraphAgents`.
- **CI:** the runner job now runs all of `tests/test_agents`, as you approved. The synthetic EXP-05 and EXP-09 checks were removed from the checkout.
- **Final test changes:** the local-auth patch target is now `OpenerDirector.open` with the same assertions. The new root-only test gives a child session 99,999 input tokens and checks the usage equals the root's own counters.
- **Claude slices:** the session-identity check runs before the raw write. Replayed receipts from a session load are discarded. The terminal receipt must be exactly one, and the stop reason must be `end_turn`. Resume requires the same credential subject. The attempt record uses `ActivityAttemptRecord.to_claude_record()`.

## Findings

**F-Q1 · question · low** (`usage.tsx:6,46`; tests at `GraphAgents.test.tsx:342-373`)
- While a run is in progress and no usage has arrived yet, the totals show `0` tokens and `$0.000000` rather than "awaiting" or "none observed".
- This is a deliberate, tested design: a capture reason or a priced-but-unknown observation does turn the totals Unknown.
- But a zero cost estimate during a live run can read as a measured value. Consider a neutral "–" or "No usage reported yet". Origin is unknown to me, since base isn't compared.

**F-Q2 · question · low** (`AgentAdvancedControls.tsx:9-15`)
- `isAgentControlHidden` exempts only `run_reference` when it has an incoming edge.
- If a legacy saved graph has a wired `output_requirements`, `request_id`, `skill_id`, `revision_id` or `bridge_url` edge, that port is hidden and the edge has nothing to attach to. The file's comment says the opposite ("connected fields remain on the normal canvas").
- The inspection-panel and edit-row callers pass no edges at all, so even a connected Prior Run is hidden there.
- If these inputs are now obsolete, document it. Otherwise exempt connected fields the same way as `run_reference`.

**F-S1 · suggestion · low** (`docker/claude/Dockerfile:5,10`)
- `npm ci --prefix /opt/acp --omit=dev` runs install scripts; the Codex image uses `--ignore-scripts`.
- The global `claude-code` install is pinned by version but not by lockfile.

**F-S2 · suggestion / question · low** (`.github/workflows/work-graph.yml`)
- Hosted CI still runs `experiments/exp100` tests from the checkout. Does that fit your rule that experiments live on `exp`? This was probably carried from before.

## Verdicts for this packet

- **Implementation: APPROVE**, with F-Q1 and F-Q2 as questions.
- **Spec:** no change. The ACP extension contract matches spec 403 (ACP-03/05/07/08), and the PR #214 link fix is still pending.
- **Visual:** source-level only, no new screenshots. Nothing contradicts the images reviewed earlier.

## Remaining gaps

- **Not read:** `SkillNodeControls`, `laomedoRecovery`, the two Claude frontend patches, `upstream.patch`, `command_mcp.py`, and the unpatched upstream adapter.
- **Tests:** the rest of the frontend suite (86 tests) and the Python test diff outside the hunks reviewed so far haven't been read as source. The architecture boundary guard and the error-catalogue coverage tests are the ones that matter most.
- **Not yet verified:**
  - the full 582-test suite at the final head;
  - wheel parity at 340 files;
  - the TypeScript baseline is still red (259 vs 265).
- **Separate work:** the migration-tool questions.
- **Approvals:** this is not approval of the whole PR or a merge. The 23 old PRs stay on hold, and your final graph inspection is still needed.