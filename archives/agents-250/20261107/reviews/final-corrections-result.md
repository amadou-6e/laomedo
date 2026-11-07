# PR250 batched correction recheck at head `a5a58ab4`

Every finding in this batch is fixed. The recheck turned up one more instance of the proxy defect that was missed: Claude's GitHub mediation sends a bearer token through the default opener (A-IF-D3). That blocks clean approval of A-IF-D1 for the Agent area. The other corrections approve.

## What I read

- **`final-corrections.diff` source and docs, lines 1–640.** That covers:
  - the OpenCode activity doc;
  - the `contract-routing` flow JSON;
  - `acp/capture.py`, the shared `activity/projection.py`;
  - the Claude command handler;
  - the Codex and OpenCode activity READMEs;
  - OpenCode `activity/models.py`, `activity/projection.py`, `auth/README.md`, `history/models.py`, `http/handler.py`;
  - the interface README, `bridge.py`, `component.py`, the output README;
  - the `join/transport.py` opener;
  - the template hash in `component-templates.json`.
- **Not read:** the test hunks from line 640 to the end, about 950 lines. They cover the new `test_acp/test_capture.py`, the bridge, transport, OpenCode history and activity tests, and the Langflow component and contract tests. I'm treating the 32, 80 and 110 passing tests as your reports.
- **Evidence:** `real-transport-reads.json`, `actual-capture-reconciliation.json`, `contract-graph-refresh-audit.json`, and the opened image `opencode-capture-final-activity.png`. I did not open `opencode-capture-final-run.json`.
- **Extra checks:** grepped every `urlopen`/`build_opener` in `src/laomedo`, then read `claude/container.py:415-434` and `work_graph/client.py:1-60`.

## Dispositions

**A-IF-D1 (bearer token through proxies and redirects): resolved for the three paths named.**
- `HttpAgentBridge` now uses one `build_opener(ProxyHandler({}), NoRedirect())` through `_open` for all six calls.
- `AgentComponent._HTTP` gains `ProxyHandler({})`, and all three direct `request.urlopen` fallbacks are gone, including the direct-runner path.
- `RunnerHTTPTransport` gains `ProxyHandler({})`.
- `real-transport-reads.json` records reading all three retained, cancelled runs through both the shared bridge and the Agent opener, with no new submission.

The grep finds the same defect elsewhere:

**A-IF-D3 · defect · medium · carried, missed by this fix**
- Where: `agents/agents/claude/container.py:420-430`.
- The Claude workspace command mediation calls plain `urlopen(Request(...))` with a `Bearer` mediator token read from `secret_path` and an `X-Laomedo-Mediator-Instance` header.
- The target is rewritten to `127.0.0.1`, but the default opener still follows environment and registry proxy settings and redirects.
- This is the same mechanism as A-IF-D1, carrying a credential.
- It belongs to the Claude provider's GitHub mediation path. Native mediation (#215) is out of scope, but sending this token correctly is not.
- Fix: use the same proxy-free, no-redirect opener.

Lower-priority instances of the same pattern:
- `agents/agents/base/agent.py:720`: a token-free health check on `127.0.0.1` through `urlopen`. A proxy could falsify the health result, but no credential is exposed. Low.
- `work_graph/client.py:32, 57`: the Langflow `auto_login` and a `Bearer` access token through `request.urlopen`. That is Shared/work-graph code outside the Agent cut, but the same defect class. Record it for the owning area.

**A-IF-D2 (interface README signatures): resolved.** The README now documents `status(provider, run_id)`, `cancel(execution_id)` and `select_artifacts(source, paths)`, and the stray heading is now a subheading. The output README now describes the function-only API.

**A-AC-Q1 (quadratic ACP capture growth): resolved.**
- For text and reasoning chunks, the capture now writes:
  - the raw `acp/sessionUpdate`;
  - one empty `item/updated` the first time it sees the item;
  - then only the new chunk, as `item/agentMessage/delta` or `item/reasoning/textDelta`.
- `finish()` still writes the full text once.
- The shared projection now applies `item/reasoning/textDelta` to `text`, the same way it already handled agent message deltas.
- Retention limits are unchanged and nothing is silently dropped.
- `actual-capture-reconciliation.json` shows, for the real run: 66 raw `acp/sessionUpdate`, 62 `item/agentMessage/delta`, 3 `item/updated`, answer matching the native record.
- The doc now separates a post-run export that ends up partial (the task outcome is unaffected) from a live protocol capture failure (execution stays unconfirmed).
- Tool-call items still re-emit the cumulative item on each update. That growth is bounded by tool output rather than every text chunk, so I'm not raising it now. It's worth watching.

**A-OH-Q1 (record usage from last message only): resolved.**
- `attempt_usage` sums every new completed assistant message for the root in the current attempt, excluding the resume baseline.
- It returns `None` if any step errored, didn't finish, or has invalid counters.
- `OpenCodeTokenUsage.from_native` validates strictly: `bool` is rejected and pydantic's `ValidationError` is a `ValueError`.
- `plus` keeps `native_total` only if both sides observed it. `to_native_payload` keeps the native field names and omits a total that wasn't observed.
- The projection reuses the same validation.
- On the real data, the root usage matches Activity (4,024 input = 982 + 3,042 cache write; 88 output). There was one assistant step, so the sum equals the old last-message value. The multi-step case is covered only by tests.

**A-OP-D1 (hard-coded uncorrelated count): resolved.** The projection counts distinct session IDs outside the verified parents from:
- otel `conversation.id`;
- `opencode/event` and `messageSnapshot` `sessionID`;
- foreign messages inside checkpoints.

Records are still excluded as before.

**A-OB-D1 and A-CH-S1: resolved.** The broker compares tokens with `compare_digest` on UTF-8 bytes. The Claude command handler sets `settimeout(5)`.

**A-IF-Q1 (raw HTTP errors from the bridge): accepted on your caller trace** (`BoundedAgentController.cancel` stores only the exception type, `run` maps to `dispatch_uncertain`, `RunnerTraceBridge.reconcile` records fixed codes). I didn't re-open `controller.py`, so this is your evidence.

**A-IF-Q2 (OpenCode cancel without a category): accepted.** Cancel is a normal outcome identified by status.

**A-OC-Q1 (default Console path): resolved in docs.** The auth README states that `console_provider()` is the default loader, that trusted host composition can inject a different one, and that the live run used an injected Go API login, so the Console database and sign-in path is **not** validated.

**A-AC-S1 and A-OU-S1:** optional, unchanged.

**Contract graph refresh:** all 10 changed paths are Skill metadata on node 1 plus `run_reference.show` on the Agent node, and the edges are unchanged (`contract-graph-refresh-audit.json`). The protected hash was updated to match the audited new graph rather than the guard being removed. The diff matches the audit.

## Screenshot

`opencode-capture-final-activity.png`:
- one turn, completed, model `opencode-go/gpt-6-luna`, captured stream complete;
- run totals 4,024 / 0 / 88 / 0 and $0.000522, matching the reconciliation;
- "2 observations · run scope";
- clear hierarchy, no overflow.

The answer text isn't visible in this crop (below the fold), so the answer match comes from the JSON.

## Verdicts for this correction packet

- **Implementation: REVISE, for A-IF-D3 only.** Everything else in the batch is **APPROVE**: A-IF-D1 for the three named paths, A-IF-D2, A-AC-Q1, A-OH-Q1, A-OP-D1, A-OB-D1 and A-CH-S1. Fixing A-IF-D3 needs a one-line opener change and a focused recheck. The low-priority health-check and work-graph cases should be recorded with their owners.
- **Spec:** no change. The ACP spec 403 (`55f6ad11`) is still an open draft.
- **Visual: APPROVE** for the final OpenCode Activity screen only.

## Still open

- **Test evidence:** the full Agent suite isn't confirmed green (one run had a `TimeoutExpired` after a host clock anomaly, and that test passed on its own later). Final-head hosted CI is pending.
- **Unread here:** the test hunks of this diff, and the provider and base READMEs beyond the auth and activity ones changed here.
- **Not retested:**
  - the default Console/app-owned OAuth path;
  - the split executor and child capture;
  - Docker down or uninstalled.
- **Known unknowns:** Claude's `evidence_complete` and resume usage are still unknown, and full TypeScript still fails on inherited diagnostics (259 vs 265).
- **Separate gates:** the whole-PR coverage audit and your graph approval. PR250 stays a draft and no old PRs are retired.