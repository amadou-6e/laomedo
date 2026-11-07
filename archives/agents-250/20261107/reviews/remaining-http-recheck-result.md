# PR250 local HTTP, correction tests and Agent READMEs at head `6018390e`

A-IF-D3 is fixed, and the local Agent traffic I checked now bypasses proxies and refuses redirects. Uncertain mediation results stay unknown and are never resent. The newly read tests check the claimed behaviour, though root-only usage has no direct test. The READMEs match the source except for two small documentation slips. Nothing in this packet blocks.

## What I read

- **`remaining-local-http.diff`, lines 1–442 (all of it):**
  - `activity/capture.py`, `base/agent.py`, the Claude `README.md` and `container.py`;
  - `host/runner/service.py`, `work_graph/client.py`;
  - `tests/support/http_server.py`, `test_transport.py`, and the new `test_shared/test_http/test_local_services.py`.
- **`correction-tests-unread.diff`, lines 1–962 (all of it):**
  - the template hash, the new `test_acp` (README and `test_capture.py`), `test_native_timeout_reconciliation`;
  - the examples `handoffs.py`, the OpenCode `test_activity`, `test_boundary` and `test_history`;
  - the orchestration `test_bridge` and `test_transport`;
  - the Langflow tests for Claude, Codex, handoff graph, integrated contract, live workgraph, OpenCode and workgraph demo.
- **`agent-readmes-current.txt`, lines 1–1054 (all 30 READMEs).** Lines 1054 onward of the workspaces README were cut off at the end of the file I was given.
- **Source checks:** `orchestration/controller.py` class and method names, and `opencode/history/models.py` method names.
- **Not opened:** the `remaining-local-http-final.log` and `-tests.log` files, `agents-final-head.log`, `wheel-result.json`.

## A-IF-D3 (Claude mediation token through default opener): resolved

- `CommandService.mediate` now uses `build_opener(ProxyHandler({}), NoRedirect())`.
- Only HTTP `400/401/403/404/409/422` return the fixed `mediation_request_refused`.
- Everything else leaves `mediation_outcome=unknown`, sets cancellation and raises the existing `claude_mediation_outcome_unknown`, with no resend. That covers a refused redirect (surfacing as `HTTPError` 3xx), any 5xx, transport failures and a bad JSON body.
- This is stricter than before, which treated every `HTTPError` as a refusal, and correctly so: a 5xx or a redirect after a POST says nothing about whether the effect ran.
- The mediator health check in the base Agent, the work-graph Langflow client, `ActivityCapture` and `RunnerService` now all use proxy-free, no-redirect openers too.
- Stable codes are unchanged. The work-graph client keeps its loopback check and its single read-only re-authentication.
- **Remaining unpatched use of the default opener in `src/`:** none in Agent code, per last packet's grep plus this diff. The Skills and GitHub local clients (`NoRedirect` only, no `ProxyHandler({})`) are recorded under #203 and outside this cut. The OpenCode Console HTTPS fetch is a remote call with different routing needs.

**A-LH-S1 · suggestion · low**
- The new tests only check refusal for 403. The other five refusal codes, especially 404, rest on the code alone.
- One question to confirm: does the mediator ever return 404 or 409 *after* attempting an effect? If it could, treating them as authoritative refusals would be wrong. That's a mediator contract question, not a problem visible in this transport code.

## Tests: real checks, not mirrors of the code

- **`test_capture.py`** (1,000 chunks of 100 bytes, for both text and reasoning). It checks:
  - exactly 1,000 raw `acp/sessionUpdate` records, each with its original chunk;
  - the live projection, built by running the shared `project()`, gives one item with the full 100 KB text;
  - after `finish`, exactly one `item/completed` with the full text;
  - the file stays under 2 MiB.

  These check raw retention, live and final projection, and the linear size bound independently.
- **`test_history`:**
  - the summed usage across steps, with exact native field names;
  - the resume baseline, giving only the last step's tokens;
  - each of missing, boolean, errored or unfinished step makes the result `None`;
  - the observed `total` is summed (18 + 18 = 36), and becomes absent when one side lacks it.
- **`test_activity`:** two distinct foreign sessions counted once each across event and otel records; foreign data stays out of items and telemetry; the existing unrelated-session case now counts 1.
- **`test_boundary`:** the wrong token and a non-ASCII token both get 403.
- **`test_transport`** and **`test_local_services`** use real local sockets:
  - patching `urllib.request.getproxies` to raise proves machine proxy settings are never looked up;
  - an environment proxy receives nothing;
  - a redirect never reaches its destination, for both GET and POST bridge calls and for mediation, login, fetch and health;
  - 403 versus 503 gives refusal versus unknown plus cancellation;
  - mediator instance identity is checked.

  `ExitStack` replaces `enterContext`, which fixes the Python 3.10 incompatibility.
- **Patch-target moves:** the test patch targets moved from `urlopen` to `_open` or `_HTTP.open`. If code went back to plain `urlopen`, these tests would make real calls and fail rather than pass falsely, and the socket tests cover the real path. I found no dropped assertions in the moved hunks. The OpenCode component test moves `run_reference` out of the hidden-field loop into an explicit `show is True` check.

**A-TC-Q1 · question · low**
- No test directly checks that `attempt_usage` excludes **child** session messages: the history tests use only the root session.
- The code takes `attempt_messages(self.root_id, …)` only, so it is correct by construction. But the "root only" claim has no direct test. Consider adding one with a child that has counters.

## READMEs (30 files, lines 1–1054)

Checked against source:
- `AgentHandoffController` is the real class in `orchestration/controller.py` (line 17), with `run`, `cancel`, `inspect`. (Your earlier note's "BoundedAgentController" was a misnaming in the prompt, not in the source.)
- The `HttpAgentBridge` signatures match the code.
- `CommandService.execute`, `mediate`, `close` and the uncertainty rule are stated correctly.
- `ClaudeTelemetry`, `HistoryReader`, `NativeExport` and the `AcpCapture` inventories match the code I read.

The docs are honest about limits:
- the OpenCode default Console path is untested;
- Claude catalogue timing doesn't add up to an end-to-end guarantee;
- shared `projection.py`/`cost.py` still contain Codex-specific interpretation, stated as unfinished work;
- the split executor's isolation is unverified (`agent-assembly.md`);
- missing pieces aren't added just for symmetry: Codex has no `auth/` package, and OpenCode states output requirements are unsupported.

**A-RD-D1 · docs defect · low** (`opencode/history/README.md:687`)
- The `NativeHistory` method inventory omits the new `attempt_usage` method (`history/models.py:188`).

**A-RD-D2 · docs defect · low** (`orchestration/README.md:935`)
- "# Handoff value vocabulary" is a second top-level heading inside the README, the same slip fixed in the interface README last packet.

**A-RD-S1 · suggestion · low**
- `activity/README.md:32-35` says "Provider-native interpretation is being separated…" in progress-report tone, unlike the declarative style elsewhere. It's accurate, so this is optional wording.

## Verdicts for this packet

- **Implementation: APPROVE** for the local HTTP changes, including A-IF-D3.
- **Tests: APPROVE.** A-TC-Q1 is optional.
- **Docs: APPROVE with A-RD-D1 and A-RD-D2** to fix; both are one-line changes.
- **Spec:** no change. The ACP spec 403 (`55f6ad11`) is still an open draft.
- **Visual:** no new UI in this packet.

## Gates still open

- **Full suite and CI:** the 582-case full suite isn't confirmed at the current head; the later HTTP changes have only 7 + 40 targeted tests. Final-head CI is still needed.
- **Wheel parity:** needs re-binding to the final source.
- **TypeScript:** still fails on inherited diagnostics (259 vs 265).
- **Not established live:**
  - native GitHub mediation (#215);
  - the default Console/app-owned OAuth path, the split executor and child capture;
  - Docker down or uninstalled;
  - multi-step OpenCode usage;
  - Claude's `evidence_complete` and resume usage.
- **Skills/GitHub:** proxy-discovery clean-up stays under #203.
- **Coverage audit:** the union across all earlier packets is still separate. This session has read the interface, provider support, ACP capture, corrections and READMEs. It has not read the earlier `prior-reviews/` and runtime packets 1–6.
- **Your graph approval:** still required. PR250 stays a draft and no old PRs are retired.