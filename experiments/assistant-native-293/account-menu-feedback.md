# Account menu and slash input feedback, 2026-11-20

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
