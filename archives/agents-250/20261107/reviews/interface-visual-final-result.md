# PR250 interface and visual packet at head `9d1b31d2`

The two visual questions and the audit question are settled, and the stable screens look right. Reading the interface source turned up one actionable transport defect (A-IF-D1): the runner bridge's bearer token can be sent to a system proxy or a redirect target. There is also a small docs mismatch (A-IF-D2). This is not approval of the whole PR.

## Rules files

- Worktree `AGENTS.md`: re-checked by grep, covering:
  - experiments only on `exp`, preserved before removal;
  - no production test fetches `exp`;
  - the reviewer workflow before merge;
  - fixtures are never acceptance;
  - Pydantic config records;
  - settings and exception rules.
- `CONTRIBUTING.md`: section headings, plus the GitHub archive section read last packet.
- Root `AGENTS.md`: not re-read this packet, only earlier in the session. I'm stating that rather than claiming a full read.

## Visual questions: A-V-Q1 and A-V-Q2 resolved

All five images were opened.
- **`codex-stable-graph.png`:**
  - real icons everywhere (sidebar, node headers, info icons, zoom bar);
  - the fresh → resume pair, with Prior Run only on the connected node;
  - nothing overlaps at 100%.
- **`claude-stable-advanced.png`:**
  - Advanced controls expanded on the fresh node (Output Continuation Retries, Runner URL, HTTP Timeout 210, Execution Timeout 180), with no Prior Run or internal fields;
  - Prior Run only on the connected resume node;
  - icons present.
- **`opencode-stable-activity.png`:** icons present, two turns completed, and the Conversation section visible (2 of 2).
- **`recovery-isolated-online.png`:** the two cards now agree.
  - The green card reads "Run outcome unconfirmed … runner is online. Check the existing run before starting new work".
  - The red card reads "The model list could not be loaded … runner is online. Open Model and use Refresh … No agent task has been submitted", with Refresh models and Dismiss buttons.
  - Neither claims the graph or task succeeded.
- **`startup-cancelled.png`:**
  - after Cancel, the card is back to the offline state ("Docker is ready, but the local runner is not running") with Start local runner offered;
  - `startup-cancellation-result.json` records `runner_start_cancelled`, a 13.8s cancel, the backend startup stopped, and no model run.

  This settles the startup-cancel path only.

## Other earlier items

- **A-I-Q2 (graph audit): resolved.** `accepted-side-graph-audit.json` shows develop changed only the four code and hash paths in the two example graphs, with no other changes, and all of them carried through. The three test-data graphs don't exist on develop.
- **AGENTS.md wording:** recorded as intentionally superseded. `literal_added_lines_preserved: false` is stated honestly. The policy fragments that matter are kept: removal only after the owning migration, an exact archive and useful regression ports; new experiments only on `exp`.
- **A-D-D2 (dangling OpenCode link):** fixed, per your report. I didn't re-read the line.
- **A-S-S1 (lock in settings):** closed. Your rationale is that mutable locks are single-owner values, not configurable fields.

## Interface source

Read in full:
- `interface/models.py:1-419`;
- `interface/bridge.py:1-298`;
- `interface/output/utils.py:1-253`;
- `interface/README.md`.

`interface/output/models.py` doesn't exist; the models live in `interface/models.py`. I did not read `output/README.md` or `langflow/README.md` this packet. Callers traced: `activity/utils.py:7-27`, which uses `AgentRequest` and `with_activity_attempt`.

**What checks out:**
- **Unknowns stay unknown.**
  - `PrecheckEvidence` keeps exact booleans and non-negative integers (rejecting `bool` passed as a count), and otherwise stores `unknown`.
  - `AgentRunReference.from_runner_status` maps `evidence_complete` to `unknown` unless it's a real boolean. Usage is `unknown` unless it's a dict, and skill use defaults to `unknown`.
  - Legacy observational fields stay `JsonValue`, so old runs aren't rejected or upgraded to success.
- **Cancellation isn't overstated.** `RunnerStatusRecord.from_snapshot` reports `incomplete` when native status is `cancelled` but `cancel_confirmed` isn't true. It always sets `executing_graph_verified=False`, and a missing snapshot gives only `pending_start`. Payload shape is preserved (`exclude_unset`).
- **Dispatch allowlist.** `AgentDispatchResult` exposes only 10 fields: no profile, auth, path or transcript data.
- **No blind resend.**
  - Transport or JSON failures after a POST become `runner_result_pending`, never a resend (`bridge.py:166-175`).
  - A 409 becomes a conflict, and an early acknowledgement with mismatched identity is refused (`:196-200`).
  - A cancel that arrives before the acknowledgement is forwarded once (`:215-217`), and poll identity is checked (`:229-233`).
- **`status()`** checks the provider and that the ID is a well-formed UUID before any request, and checks the response identity afterwards.
- **`with_activity_attempt`** spreads `self.payload`, which would fail if the payload were `None`. Its only caller (`activity/utils.py:24`) runs it only for `resume`, which always has a POST body, so this isn't actionable today.
- **`output/utils.py`** is a byte-identical move (your report). It looks the same as the accepted behaviour:
  - closed requirement fields;
  - `task_outcome` forced to the `success`/`failure` enum;
  - `success` downgraded to `unknown` unless the executor reported `completed`;
  - precheck responses never echo the submitted values.

**A-IF-D1 · defect · medium · pre-existing, now on the shared interface (this settles old note I3)**
- Where: `bridge.py:93, 162, 222, 252, 277, 295`, which all use the default `urllib.request.urlopen`.
- Mechanism: the default opener reads proxy settings from the environment *and*, on Windows, from the registry (`getproxies_registry`). The loopback check in `__init__` validates the URL string, not where the request actually goes.
- Trigger: a machine with a system or corporate HTTP proxy that doesn't exclude `127.0.0.1`/`host.docker.internal` (the Windows registry bypass only covers `<local>` names without dots).
- Effect: the runner bearer token from `_headers()` could be sent to that proxy.
- A second path: the default redirect handler follows redirects and (as far as I recall) copies non-content headers to the new request. I'm inferring that from urllib's behaviour; please confirm.
- This is not cosmetic. The GitHub side already uses `NoRedirect` (`laomedo.http.redirect`).
- Fix: use one opener, `build_opener(ProxyHandler({}), NoRedirect())`, for every bridge call, plus a test that a proxy setting in the environment is ignored.

**A-IF-Q1 · question · low (old note I4)**
- `status()`, `cancel()`, `select_artifacts()` and `lookup_request()` (other than its 404/409 handling) let raw `HTTPError`/`URLError` propagate instead of mapping them to a stable `HandoffError` code.
- This only matters if a caller turns the exception text into a user-facing message. The large caller grep was cut off, so I couldn't confirm the caller handling. Please name the caller that catches these.

**Old note I5 (Content-Type on GET with no body): not actionable.** It does no harm.

**A-IF-D2 · docs defect · low**
- `interface/README.md:22-24` documents `status(reference)` and `select_artifacts(reference, selection)`. The code takes `status(provider, run_id)` and `select_artifacts(source, paths)`.
- The same file also contains a second top-level heading, "# Structured output contracts" (line 34), which looks like merged content.
- The method table needs to match the real signatures.

## Evidence records read (facts as recorded, not my own observation)

- **Stop:**
  - Codex: cancelled, confirmed, `cancelled_by_user`, controller cleanup confirmed;
  - Claude: cancelled, confirmed, `claude_cancelled`, descendant cleanup verified;
  - OpenCode: cancelled, confirmed, controller cleanup confirmed, but `error_category: null`.

  **A-IF-Q2 · question · low:** the OpenCode cancel has no cancellation category, unlike the other two. Is that intended for presentation, and does the UI still route it as cancelled?
- **`cleanup-final.json`:** every recorded Codex and Claude container (8 in total) is absent, and the pending receipt directories are empty. It lists no OpenCode owned containers, only OpenCode receipt paths. Presumably OpenCode is covered by its controller cleanup, but that isn't shown in this record.
- **Model Refresh:** HTTP 200 for all three, with selections kept (gpt-6-luna, Haiku, opencode-go/gpt-6-luna) and no new native run.
- **Wheel at `bb331f54`:** 339 files, none missing or changed. Imports load from outside the checkout.
- **Deployment parity:** checked at `4b81988b`, not the current head: 2,777 frontend files, nothing missing, different or extra, with CRLF line endings normalized only.
- **`interaction-final-tests.json`:** 6 suites and 86 tests, all passing. They include the connected-only Prior Run port, "healthy API does not turn catalogue failure green", and "unrelated startup crash not presented as successful cancel". These are internal tests.

## Verdicts for this packet

- **Interface implementation: REVISE**, for A-IF-D1 (token can reach a proxy or redirect). Models, unknown-value handling, cancel and identity checks, and output validation are **APPROVE**.
- **Interface docs: REVISE**, for A-IF-D2 (one table).
- **Spec:** no change. The ACP spec 403 (`55f6ad11`) is still open as a draft. Native mediation (#215) is excluded.
- **Visual: APPROVE for:**
  - the stable Codex graph;
  - the Claude advanced and resume graph;
  - the OpenCode resume Activity;
  - the consistent recovery cards when online;
  - the startup-cancelled state.

  This is not full UI approval or a claim that any task succeeded.

## Gates still open

- **This packet:** fix A-IF-D1, then a focused recheck. A-IF-D2 needs its doc fix, and A-IF-Q1 and A-IF-Q2 need answers.
- **Not retested:** Docker down or uninstalled, the split executor, child-agent capture, and app-owned OAuth.
- **Not established:**
  - Claude's `evidence_complete` (still `unknown`) and complete Claude resume usage;
  - a green full TypeScript check (still 259 vs 265 inherited diagnostics).
- **Whole-PR coverage:** the final audit across `prior-reviews/`, runtime packets 1–6 and conservation is still separate and not done. Not read this packet: `output/README.md`, `langflow/README.md`, the root `AGENTS.md`, and the bridge's construction and exception-handling callers.
- **Before merge:** ACP spec 403 and your browser validation of the final workflows. PR250 stays a draft, and no old PRs are retired.