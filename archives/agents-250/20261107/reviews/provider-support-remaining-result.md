# PR250 provider support packet at head `9d1b31d2`: all 2,432 lines read

I read the whole prepared file, so the 24 provider support files are now fully covered. Credentials stay out of public records, native session identity holds, and partial telemetry is reported as unknown. Four low-to-medium problems need attention: one possibly undercounted usage field and three small hardening gaps. Your notes say `ec6c721c` doesn't change these files.

## What I read

`provider-support-remaining.txt` in four chunks (1–600, 601–1200, 1201–1800, 1801–2432). Source ranges:

| File | Lines |
| --- | --- |
| `claude/cli.py` | 1–70 |
| `claude/auth/settings.py` | 1–70 |
| `claude/auth/errors.py` | 1–14 |
| `claude/utils.py` | 1–138 |
| `claude/activity/models.py` | 1–41 |
| `claude/activity/settings.py` | 1–75 |
| `claude/activity/telemetry.py` | 1–227 |
| `claude/activity/utils.py` | 1–18 |
| `claude/activity/http/handler.py` | 1–78 |
| `claude/activity/http/server.py` | 1–20 |
| `claude/http/handler.py` | 1–47 |
| `claude/http/server.py` | 1–19 |
| `opencode/history/reader.py` | 1–314 |
| `opencode/history/models.py` | 1–222 |
| `opencode/history/settings.py` | 1–48 |
| `opencode/history/errors.py` | 1–13 |
| `opencode/models.py` | 1–96 |
| `opencode/utils.py` | 1–89 |
| `opencode/settings.py` | 1–22 |
| `opencode/activity/models.py` | 1–34 |
| `opencode/activity/projection.py` | 1–500 |
| `opencode/activity/telemetry.py` | 1–152 |
| `opencode/http/handler.py` | 1–58 |
| `opencode/http/server.py` | 1–19 |

Rules files: I relied on the copies you supplied earlier and didn't re-open them.

## Findings

**A-OH-Q1 · question · medium · carried** (`opencode/history/models.py:166-168`)
- `record_fields` sets the run record's `usage` from the **last** assistant message's `tokens` only.
- Trigger: an OpenCode turn with tools. Each step produces its own assistant message with its own counters.
- Consequence: the `usage` on the record, which feeds the public reference's `usage` field, could undercount the attempt.
- The Activity projection, by contrast, adds up every completed assistant message (`projection.py:265-295, 344-348`). So the record and Activity could disagree.
- Is `usage` on the record meant to be per-message or per-attempt? If per-attempt, add up `attempt_messages(root)`, and record unknown if any message lacks counters.

**A-OP-D1 · defect · low · carried** (`opencode/activity/projection.py:410`)
- `uncorrelated_thread_count=0` is hard-coded.
- But `opencode/event` records whose `sessionID` isn't a known descendant are silently skipped (`:90-91`), and so are otel records outside `parents` (`:75`).
- Consequence: Activity can report "0 uncorrelated threads" even when native records were dropped, which overstates how complete the correlation is.
- Fix: count the distinct skipped session IDs, or report it as unknown.

**A-OB-D1 · defect · low · carried** (`opencode/http/handler.py:31`)
- The broker checks its bearer token with `!=`.
- The Claude handlers use `secrets.compare_digest` (`claude/http/handler.py:25-27`, `claude/activity/http/handler.py:32-34`).
- The broker is reachable from the isolated controller over `host.docker.internal`, so use a constant-time comparison here too.

**A-CH-S1 · suggestion · low** (`claude/http/handler.py:23-47`)
- The Claude command handler sets no socket timeout. The telemetry and broker handlers set `settimeout(5)`.
- A stalled container client could hold a handler thread indefinitely.

**A-OU-S1 · suggestion · low** (`opencode/utils.py:49-62`)
- Two small hardening gaps in `_credential_binding`:
  - it reads `auth-validity.json` without an encoding and without mapping errors, so malformed JSON or a missing key raises a raw error instead of a stable code;
  - if two processes create the key file at once, one can read a zero-length file and fail with `opencode_credential_binding_key_invalid`.
- Both fail closed, so this isn't a safety issue.

**A-OC-Q1 (Console default path): settled as an untested default.**
- In production, the Console account database and `/api/config` path (`opencode/auth/utils.py`, read last packet) runs whenever no `provider_loader` is injected.
- The live runs injected the Go API key path instead, so the Console path is not covered by live evidence.
- Its safeguards hold:
  - read-only SQLite;
  - https `opencode.ai` only;
  - no redirects;
  - placeholder credentials rejected;
  - at least 60 s of token validity required (`check_auth_fresh` requires 210 s before launch);
  - organization must match;
  - routing, SDK packages and endpoints allowlisted.
- Recommend stating in the OpenCode docs that the Console path is the default and is untested live.

## What checks out

- **Credentials:**
  - The Claude telemetry token is a `SecretStr`, excluded from dumps and unwrapped only into the native exporter's environment. Content logging is turned off: prompts, responses, tool details, tool content and account UUID.
  - The OpenCode broker token is a `SecretStr`, unwrapped only in `to_config`.
  - Claude login settings read only explicit arguments and the process environment (no dotenv or secret store), and are hidden from repr and dumps.
  - `credential_binding` is an HMAC fingerprint, never login material.
- **Native history:**
  - `_check_credentials` requires the account, credential and state tables to exist **and be empty**, and refuses any non-empty table that has secret-like columns (excluding session token counters).
  - The copy is made in memory, then `VACUUM INTO` writes it out, which drops deleted pages.
  - The export container has no network, runs as UID 10001 and receives no credentials.
  - The session ID must match `ses_[A-Za-z0-9]+`.
- **Session and descendant binding:**
  - `NativeExport.bind` checks the session ID, parent, message and part identity, and rejects duplicate messages.
  - Children are followed only through native `task` metadata that names this exact parent.
  - Cycles and conflicting parents are refused, with a limit of 32 sessions, 8 MiB, and a whole-tree deadline that reserves 15 s.
  - A child created before the attempt's first user message raises "child usage baseline is unknown" rather than charging it to this attempt.
  - Resume counts only new message IDs (`attempt_messages`), and `retain` checks the root and baseline identity.
- **Cleanup uncertainty:** `CleanupUnconfirmedError` becomes `opencode_container_cleanup_unverified`, and the private copy is kept because a job may still reference it.
- **Telemetry:**
  - The Claude receiver is authenticated (constant time), has a 5 s socket timeout and limits uploads to 8 MiB and 4,096 records.
  - It keeps only allowlisted attribute keys and known event names, never log bodies.
  - A record whose native `session.id` doesn't match is flagged `scope_conflict` rather than reassigned.
  - Any failure sets `failed`.
  - Closing it raises `receiver_close_unconfirmed` if the receiver thread doesn't stop.
  - The OpenCode span exporter uses `trust_env=False`, so environment proxies are ignored there, and it checks the exported span count.
- **Usage and cost:**
  - In the projection, an errored or incomplete assistant message, or a missing counter category, makes that total unknown.
  - An incomplete export makes the thread and attempt usage unknown.
  - Cost requires the observed model plus a full set of prices, and otherwise is `None` with a reason.
  - Overlapping input categories are refused.
  - Claude's `activity_usage` behaves the same way (checked last packet).
- **Models and defaults:**
  - Claude models come only from native discovery. Models without effort support get `["default"]` (meaning "don't pass `--effort`"), and the advertised effort levels are validated.
  - OpenCode `model_metadata` requires each `provider/id` to match its metadata and refuses an empty list or duplicates.

## Verdict for these 24 files

- **Implementation: APPROVE with follow-ups.**
  - A-OH-Q1 (record usage) and A-OP-D1 (hard-coded uncorrelated count) bear on honest reporting of usage completeness, so fix or explain them before final acceptance.
  - A-OB-D1 and A-CH-S1 are small hardening fixes.
  - A-OU-S1 is optional.
- **Spec:** not assessed. The ACP spec 403 (`55f6ad11`) is still an open draft.

Coverage of these 24 files is complete. Still pending elsewhere:
- the A-AC-Q1 fix recheck (work in progress);
- the A-IF-D1 transport fix recheck;
- the provider and agent READMEs, which weren't in this packet;
- child capture, Docker down or uninstalled, the split executor, and app-owned OAuth/Console;
- Claude's `evidence_complete` and resume usage, still unknown;
- the whole-PR coverage audit;
- your graph approval.