# AB-01 recheck, CAT-Q1 and the remainder of the initial extraction

AB-01 is fixed, CAT-Q1 is closed, and the remaining extraction hunks I read contain no regressions. Two docs passages still describe retired roles as delivered or as the current API, so docs need a revision (DOC-01, DOC-02). This is not whole-PR, owner or merge approval. Canonical spec PR 403 and the owner's final graph acceptance remain separate.

## 1. AB-01 (OpenCode per-thread cost): verified fixed

- **Fix** (`opencode/activity/projection.py:362-369`): if a thread's usage is unknown, its cost estimate is now unknown too, with the reason "Thread token usage is incomplete." An estimate that was already unknown keeps its original reason.
- **Incomplete exports:** in that case `per_thread` becomes `dict.fromkeys(parents)`, so every thread's usage is `None` and the same guard makes every thread's cost unknown.
- **New test:**
  - the positive control (one completed, priced message) keeps a known amount;
  - three cases each make that thread's usage, per-thread cost and overall cost unknown, with the exact reason:
    - an aborted peer message;
    - an unfinished peer message;
    - a peer with invalid token counts.
- The README addition describes this rule accurately.
- **CK-02 is fixed:** the concern README now says five contracts in total, and the false statement about current leaks is gone.
- **CK-01 (relative-import support)** remains an optional limitation of the structural guard. No current provider bypasses it, so I'm not requiring a parser change.

## 2. CAT-Q1 (Codex model payload): closed

- The extracted methods from blob 089f show that before the extraction, `models()` returned only `id` and `efforts`, and `model_catalog` passed that through unchanged.
- Today `to_payload(include_model_names=False)` still sends `id` and `efforts`. The newer native metadata stays inside the Python catalog.
- No existing field was removed from the wire.
- I did not read `host/runner/http/handler.py`; that it calls `editor_model_catalog` comes from your statement.

## 3. Remaining initial-extraction hunks

**Source:**
- **Mechanical moves:**
  - `EFFORTS` and the catalog TTLs moved into the provider `settings.py` files (300 s for Claude, 30 s for Codex and OpenCode), matching the old inline values;
  - `ROLE_INIT_LOCK` is now in `base/settings`;
  - the component and `claude/utils` imports moved with them.
- **CLIs:** both CLIs now build their Agent through `AgentProviderRegistry.create_agent`.
- **`check_auth_fresh`:** its new `minimum_validity_seconds` can only raise the required validity above `MIN_TOKEN_REMAINING_MS`, never lower it.
- **Error catalog:** the new `credential_constraints_unsupported` entry says correctly that no refresh or model task was started.

**`routes.py` (now read in full):**
- reads are owner-scoped and return 503, 401 or 404 where appropriate;
- responses are no-store and nosniff;
- when a detail, boundary or capture limit is hit, usage and cost are made unknown and `per_thread` is emptied;
- the initial hunk only added `provider=` and docstrings.

**Shared Activity extraction (`roles-activity.diff`):**
- the old shared projection's helpers (`_parent`, `_telemetry`, `KEYS`) and its assembly tail are identical to the current `codex/activity/projection._parent`, `utils.normalize_telemetry` and `timeline.py`;
- the old file priced every provider with the Codex `activity.cost` table (`:265`, `:330`) and treated `claude/result` as a diagnostic for every provider (`:125`);
- the extraction deliberately limits Codex prices to Codex and `claude/result` to Claude. That is the intended removal of the Codex price fallback, not a regression.

**Tests (all hunks at `:716-1347` and `:1392-2006`):**
- The edits rename to the new owning modules:
  - `CodexController` → `CodexAgentRuntime`;
  - `ClaudeContainer`/`CommandService` → `ClaudeRuntimePolicy`/`ClaudeCommandExecutor` plus its transport;
  - `IsolatedOpenCode`/`CommandBroker` → `OpenCodeAgentRuntime`/`OpenCodeCommandExecutor` plus its broker;
  - `close` → `shutdown`;
  - `stop` → `request_cancel`;
  - `exec_probe` → `execute(CommandRequest(argv=...))`;
  - the private catalog fields now live on `catalog`.
- Every assertion is kept:
  - error codes;
  - privacy and loopback checks;
  - 403 without a token;
  - worker-busy refusal;
  - cleanup reported as unverified;
  - the order stop, drain, then recover;
  - mediation outcome unknown vs refused;
  - fixed-argv preflight;
  - endpoint pinning;
  - the error-producer and settings-consumer path lists, which now point to the new owners.
- `test_acp_controller` now calls `close` only if the controller isn't already closed. This doesn't weaken any assertion.
- The `test_interfaces` change exempts `laomedo.agents.registry` from the models-import scan and adds `agents.models` to the field-description check. That's correct.
- No test was weakened, and no dead test checks a retired object.

## Findings

**DOC-01 (Low–Medium, current docs): the parity plan says retired roles were delivered.**
- `docs/architecture/agent-provider-parity-plan.md:35-38` says "#275 delivers explicit runtime … and Activity roles".
- The runtime role (`BaseAgentRuntime`/`RuntimeLaunch`) and the Activity projector role were later withdrawn:
  - `provider-boundaries.md:300` says `BaseAgentRuntime` and `RuntimeLaunch` were retired;
  - `activity-interface.md:214-216` says the projector classes and registry methods were removed.
- The same plan's target tree still lists `base/runtime.py # BaseAgentRuntime` (`:77`) and its step 3 still says to adapt the implementations to it (`:154`). It has no "superseded" banner.
- **Fix:** add a status note there, like the one in `provider-interface-alignment.md`, and say which roles were delivered and which were withdrawn.

**DOC-02 (Low, current docs): two docs give the old catalog method name.**
- `src/laomedo/agents/agents/README.md:35` lists `discover(refresh=False)`.
- `provider-interface-alignment.md:19` lists `discover` too. That file does carry a banner saying it is historical analysis.
- The actual method is `list_models(refresh=...)`, so readers of the current README are pointed at a method that doesn't exist.

## Verdicts

| Area | Verdict |
|---|---|
| AB-01 | Fixed; **APPROVE** |
| CAT-Q1 | Closed |
| Implementation (remainder hunks read) | **APPROVE** |
| Tests | **APPROVE** |
| Spec | N/A here (PR 403 is separate) |
| Docs | **REVISE**: DOC-01, DOC-02 |

## Coverage

- **Read:**
  - all of `activity-ab01-correction.diff`;
  - `cat-q1-exact-methods.md`;
  - `routes.py` in full;
  - `roles-final-remainder.diff:1-586` (source and docs) and `:716-2006` (tests);
  - `roles-activity.diff:25-84` and `:390-514`, plus a search of the old body;
  - the current docs status lines listed above.
- **Not read:**
  - `projector-records.json` (diff `:587-715`);
  - `claude-template.json` and `claude.json` (`:1348-1391`);
  - the migration-map hunks in this diff from `:2007` on (packet C covered the same maps up to `roles-checker.diff:1129`);
  - `roles-activity.diff:85-389` line by line (I only searched it);
  - `roles-activity.diff:515-1086` (the new `timeline.py`, which I read in its current form in B, and the Claude/Codex hunks);
  - `activity-ab01-shared.log`;
  - `handler.py`;
  - `AGENTS.md` (not re-read).
- Nothing here is approved on the basis of those unread files.