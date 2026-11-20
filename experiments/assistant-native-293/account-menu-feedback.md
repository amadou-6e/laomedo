# Account menu and slash input feedback, 2026-11-20

## Owner-selected account defaults (feedback19-22)

The owner superseded mandatory explicit selection: new chats should default to
an available account. Source56479f074 defaults the first connected ready account
for the current profile/provider and preserves explicit choices and existing chat
bindings. The removed selection sentence is replaced by placeholder/trigger
Select an account or No account available. Without a binding, no stale model or
effort appears. Same-account reselection no longer clears models.

71assistant UI tests PASS, including profile-list fencing (a new test caught stale
model discovery before the account-owner guard was complete), ready-only defaults,
explicit override/list refresh and empty state. Build PASS1m17s; CI PASS at source
head. Specification5bbd464 updates contract and editable AC-293; validator1845
files/6projects/0errors. No Python changes; prior94backendtests remain historical
unchanged-backend evidence, not a new run.

Real shared integrated browser: new chat defaulted the actual saved Codex account,
loaded models, enabled Send for an unsent test draft, and opened the model/effort
popover. Switching to unconnected Claude showed No account available, disabled
Send and no stale effort. Returned to Codex; test draft cleared without sending.
No prompt/native command/graph executed. Actual full-view screenshots are private
ignored review artifacts, never archive attachments. Existing user conversation
and saved account preserved; stable preview port and tab reused.

Same Claude session reviewing implementation2957a6e3a..56479f074, specification
4f49b1e..5bbd464 and three actual images; this delta is fully unreviewed, reviewer
pending. Earlier approvals do not cover it; nothing merged.

Final same-session review of56479f074 / spec5bbd464: Implementation APPROVE with
71UItest/build/CI conditions fulfilled; Specification APPROVE. All three actual
desktop dark images inspected and matched. Visual INCOMPLETE for narrow/light/
focus states. Optional A1-A3, no blockers. No source changes after review; both
existing PRs updated, nothing merged. UI left on Codex with its default account
and discovered models; no test draft or extra model prompt remains.

## Completed reviewer correction

After quota restoration, the same Claude reviewer approved the UI corrections
and specification4f49b1e, but found S1: logout could await a failing database
before removing tool authority. Correction38253df86..2957a6e3a now fences known
raw/provider/canonical identities and removes contexts/tokens synchronously,
then persists revocation with cleanup in finally. Lookup/write failure and
event-gated timeout cancellation tests pass with actual signed-token refusal.
Eight concurrent first renewal admissions pass on file-backed SQLite.

Focused reviewer recheck: S1 verified-fixed, S2 settled for SQLite; Implementation
APPROVE at2957a6e3a, conditional on fullsuite and Black, both now met:94assistant
tests PASS214.055s, Black956 PASS, all required CI PASS. UI686tests and final
build remain unchanged frontend evidence. Specification APPROVE4f49b1e. Visual
INCOMPLETE; no new live logout/provider checks claimed. No source changes after
review, and no merge performed.

Remaining limits: an unseen renewal lost before persistence cannot recover the
earlier approval root; failed durable revoke can lose its memory-only fence at
restart. Per-item native cleanup may still stall or stop on an error; safe alias
pruning requires expiry accounting. These were disclosed, nonblocking review
items. The existing integrated preview was left running to preserve the working
user session; the later logout-only source correction was not loaded into it.

## Later renewal fix and explicit restart limitation

The earlier UI-only checks below are historical evidence, not the final backend
claim. At dbe659501 the real preview exposed a normal app-JWT renewal bug: pending
native approvals became unavailable after reload. The correction preserves the
verified browser lease with durable fingerprint aliases, including logout via
an unseen renewed token. No bearer is stored. All 91 assistant backend tests pass
(230.029s), including actual signed JWT verification, real ProviderConnections
renewal/reconstruction, SQLite expiry/owner/collision/revocation checks. Black956
and CI pass at that head.

Real integrated-browser check at dbe659501: a fresh /mcp proposal retains enabled
Approve/Reject after reload. Read-only owned database audit reports two verified
renewal aliases for the proposal root, pending state and authority not revoked.
The proposal was not approved or executed. Screenshot stays private/ignored.

An additional ordinary send after the preview SERVER restart refused with the
existing Codex resume_after_runner_restart_forbidden safeguard, before another
model turn. This is not a successful send or a JWT failure. The current spec
explicitly preserves runner-restart fail-closed rules. We did not weaken it.
38253df86 adds the missing human-readable error/recovery and a real shared error
renderer test. Updated frontend build PASS1m19s; 686 tests across assistant and
shared error rendering PASS (17 suites; includes 69 assistant UI tests). New
linked conversation returned ACCOUNT-FINAL-SEND-293. The real database read
confirms completed, no error and exact marker response. The final built error
copy was visibly verified in the old chat, then the fresh working chat reopened
in the same integrated CoBrowse tab. No transparent continuation
after authenticated runner restart claimed. Earlier conversation remains intact.

Claude correction recheck is quota-blocked until18:50 Berlin. Initial UI review
covered cbb110473..9296cc4fa with REVISE; d4feb411f corrections await recheck.
The later auth fix and restart-error copy are fully unreviewed, reviewer pending.
Specifications 4f49b1e define the durable renewal/logout invariant; validator1845
files/6projects/0errors. Nothing merged.

Source cbb110473..9296cc4fa implements compact account rows, shared provider icons, a selected-row highlight, separate account-settings footer, aligned welcome cards, explicit blocked-send guidance and draft preservation. Review correction d4feb411f reserves AP-2 candidate command names across Codex, Claude and OpenCode and improves the account trigger's accessible description. Spec head f536052 records those definitions.

## Actual integrated-browser acceptance

Rendered build9296cc4fa on the normal saved-account preview. Selected unconnected Claude: visible named account guidance, disabled model picker/Send, editable draft. Switched to connected Codex, explicitly selected its real saved account, observed discovered models. Submitted a fresh ordinary message and received ACCOUNT-MENU-SEND-293. A deliberate /status extra refusal disabled Send; editing to /sta immediately removed that definite input error and re-enabled Send. /sta was submitted as an ordinary model message and received a response. Selected real /mcp from the observed slash menu and submitted it: a durable Run /mcp approval card appeared, with Approve/Reject. It was NOT approved or executed by this acceptance. No graph edited/run. Selected final native receipt: two model turns, zero executed native commands, completed and controller/Docker cleanup confirmed. User-owned history preserved.

A fresh browser read verified all five supported Codex command previews before session creation; only initial status is selectable, other previews are disabled until native advertisement. This is findability, not cold execution of all commands. The existing initial-status lifetime contract remains unchanged. Screenshots are private ignored local review artifacts, never publication attachments; account display identifiers are not archived here.

## Checks and limits

69 assistant UI tests pass at d4feb411f through the exp-only pinned preview Jest wrapper (Windows root matching and real remark-gfm ESM transforms; no new message-render mocks). Build9296cc4fa passed in1m16s; reviewed-correction build is running. Spec validator1845files6projects0errors. Existing backend820tests/4skips pass cbb110473; this feedback delta changes no Python or adapters. Required exact-head CI to be recorded after completion.

Claude initial review cbb110473..9296cc4fa: Implementation REVISE U1 (known-command guard was Codex-only), Specification REVISE (define each provider's known names), Visual INCOMPLETE although actual full-window captures matched the requested appearance. Corrections/tests/source evidence await focused recheck. No merge performed. No live Claude/OpenCode execution or narrow/light-theme acceptance claimed.

## U2 parser evidence (zero model calls)

Normal assistant payload prepends ASSISTANT_INSTRUCTIONS and User message before text (runtime._job). Shared ACP transport sends one complete text block. ClaudeAgent._prompt additionally JSON-encodes the task for ordinary calls, then passes that unchanged to client.prompt. Claude ACP0.98.0 local command checks use leading/exact matches: firstText.startsWith('/'), parseMcpCommand trimStart startsWith('/mcp'), isUsageCommandText exact '/usage', promptToClaude MCP rewrite anchored at start/end. They do not turn an interior slash line into a native operation.

OpenCode service detectSlashCommand joins all text, trims it and returns immediately unless startsWith('/'); only a detected command reaches session.command, otherwise session.prompt. Inspected opencode-service.ts exactly matches public anomalyco/opencode v1.18.33 packages/opencode/src/acp/service.ts after newline normalization, SHA256238750d52e220080db7b7f4992432fbfc7fb7ec5a15a6175460f8f0832a2c8de. The local Claude package metadata identifies0.98.0, matching the Docker lock.

check-prefixed-slash.cjs extracts the actual inspected native parser function bodies with TypeScript and runs them without dependencies or provider access: six prefixed cases across OpenCode slash, Claude MCP and Claude usage parsers (18 assertions), plus three bare-command positive controls PASS. No model/native API calls. It does not prove the entire SDK/live provider flow and is not presented as that acceptance. Evidence source hashes are printed by the harness. Production tests do not import or fetch exp.
