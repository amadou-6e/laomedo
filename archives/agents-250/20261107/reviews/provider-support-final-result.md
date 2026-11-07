# PR250 provider supporting-source packet at head `9d1b31d2`: partial coverage

I read only part of this packet within the time bound. Most of the listed files are still unread, so the verdict below covers only what I read. Nothing I read leaks credentials, changes native session identity or invents model defaults. One question needs an answer: long ACP answers may hit the capture size limit and fail (A-AC-Q1).

## Rules files

I did not re-read the root or worktree `AGENTS.md` or `CONTRIBUTING.md` in this packet. I relied on the grep of the worktree `AGENTS.md` and the `CONTRIBUTING.md` headings from the last packet. That doesn't meet your request to read them explicitly.

## Read in full

- `agents/activity/acp/capture.py:1-220` and `acp/settings.py:1-4`.
- `agents/agents/opencode/auth/utils.py:1-150` and `auth/transport.py:1-11`.
- `agents/agents/claude/agent.py:1-194`, which completes the earlier 195–1326 coverage at the start of the file.
- `agents/agents/claude/catalog.py:1-3`.

## Read in part

- `agents/agents/claude/utils.py`:
  - `activity_usage` (lines 11–51);
  - `terminal_result` (65–87);
  - `normalize_models` (90–130). The tail after line 130 is unread.
- Callers: `opencode/agent.py:397-405` (where the capture is created and bound) and `opencode/boundary.py:575-583` (`capture.finish` and the terminal status).

## Findings

**A-AC-Q1 · question · medium · carried (capture.py existed before; I'm reading it in full for the first time)**
- Where: `acp/capture.py:118-183` together with `:57-68`.
- Mechanism:
  - Each agent text or reasoning chunk appends the chunk to `item["text"]` and then writes an `item/updated` record holding the *entire* text so far, besides the raw `acp/sessionUpdate` record.
  - Retained bytes therefore grow roughly with the square of the answer length.
  - For example, a 100 KB answer streamed in 1,000 chunks writes about 50 MB of `item/updated` records, which exceeds `MAX_ATTEMPT_BYTES` (20 MiB).
- Trigger: a long streamed answer or long reasoning on OpenCode through ACP, the only constructor I found (`opencode/agent.py:401`).
- Effect: `_write_records` raises `ValueError`, and the comment says this "propagates through the ACP client". I didn't trace whether that propagation:
  - only marks capture `partial`, which would be correct; or
  - fails or aborts the native turn, which would contradict "capture failures do not change task success" in `providers/opencode/activity.md`.
- Please show the boundary's handling of an exception raised inside the ACP update callback, or add a test for an answer over 20 MiB of cumulative updates. Writing only the new chunk in each `item/updated` and the full text at `finish` would remove the growth.

**A-AC-S1 · suggestion · low**
- `update()` and `finish()` check the session ID before checking `sealed`. A late update from a different session after cleanup raises "session mismatch" instead of being quietly ignored.
- That fails safe, but it could turn a harmless late notification into a capture error. Ignoring the update when sealed first would avoid that.

**A-OC-Q1 · question · low · carried**
- Where: `opencode/auth/utils.py:29-149`, `console_provider`.
- This function reads the access token and active organization from the OpenCode Console account database (read-only SQLite). It then fetches `/api/config` from `opencode.ai` with the token as a bearer header.
- Good points:
  - it pins the origin to https `opencode.ai`, with no credentials, query or fragment in the URL;
  - it rejects redirects (`NoRedirect`);
  - it rejects placeholder credentials (`CANARY-`, `***`, `[redacted]`);
  - it requires the token to have more than 60 s of validity left, an exact organization match, and allowlisted routing, SDK packages and model endpoints.
- I saw no logging. The secrets are returned to the caller.
- Two questions:
  1. The integration record says the live runs used "the selected Go API login in a dedicated private profile; no Console account database … was required". Is this Console path still reachable by default, or only an explicit fallback? Which caller selects it?
  2. A non-dict response raises `AttributeError` instead of a stable code. That fails closed, so it's minor.

## What checks out in the code I read

- **Claude model catalogue:**
  - it uses only the native `initialize` control request, with no session persistence, tools, MCP servers or permission prompts;
  - the response is size-bounded at 1 MiB and identity-checked;
  - exactly one response is required.
  - `normalize_models` keeps the native IDs, labels and advertised effort levels, rejects anything malformed, and adds no default models or efforts.
  - Concurrent refreshes share one in-flight `Future`. A waiter times out at 65 s, which exceeds the discovery bound (15 s auth plus 45 s CLI). A failure is passed to the waiters, and the pending slot is cleared in `finally`.
- **`activity_usage`:**
  - returns `None` (unknown) whenever any usage category is missing or invalid;
  - converts input tokens so cache reads and writes are counted;
  - adds reasoning only when every model reports it within its output tokens;
  - does not add resumed totals together.
- **`terminal_result`:**
  - requires the native `result` record, a matching `session_id`, `success`, at least one turn and no spawned subagents;
  - an empty answer becomes `completed_without_agent_message`;
  - it never repairs an answer.
- **`prepare_resume` and `recover_interrupted`:**
  - validate the timeout and mirror the login before resume, using the same minimum validity;
  - cleanup reconciles only the exact recorded container identity and records `container_cleanup_unverified` if needed.
- **`AcpCapture`:**
  - binds a single native session;
  - labels the host-assigned turn ID as host provenance;
  - redacts each record (`sanitized`) before writing;
  - validates the whole batch before writing anything;
  - keeps metadata appended after cleanup separate and allowed only once sealed;
  - never invents a completion: `finish` records the given status and usage as-is.

## Not read (most of the requested packet)

- **Claude:** `cli.py`, `auth/settings.py` beyond the reviewed `MIRROR_LOCK` hunk, `auth/errors.py`, the rest of `utils.py`, `activity/{models,settings,telemetry,utils}.py`, `activity/http/{handler,server}.py`, `http/{handler,server}.py`.
- **OpenCode:** `history/{reader,models,settings,errors}.py` (I only checked `settings.py` budgets in an earlier packet), `models.py`, `utils.py`, `settings.py`, `activity/{models,projection,telemetry}.py`, `http/{handler,server}.py`.
- **Shared and docs:** `agents/agents/base/README.md` and the provider READMEs.
- **Evidence:** `live-runs.json` and the native-facts files were not re-read.

## Verdict

- **Implementation: INCOMPLETE.** For the files I read, I found no credential leak, identity change or invented default. Pending: A-AC-Q1 (medium question) and A-OC-Q1, and most of the packet is unread.
- **Spec:** not assessed. The ACP spec 403 (`55f6ad11`) is still an open draft.
- **Separately pending:**
  - the A-IF-D1 transport fix;
  - child capture, Docker down/uninstalled, the split executor and app-owned OAuth;
  - Claude's `evidence_complete` and resume usage, both still unknown;
  - the whole-PR coverage audit;
  - your workflow validation.

A follow-up packet covering the unread Claude and OpenCode activity, history and http files is needed before calling provider supporting-source coverage complete.