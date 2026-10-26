# Codex activity parity verification, 2026-10-26

Issue: [#191](https://github.com/amadou-6e/laomedo/issues/191).
This repairs the original Codex node's existing shared Activity view; it does
not introduce another agent node or a separate viewer. The PR records the
reviewed and tested revisions against develop `7852666`.

## Genuine local integration

The original `LaomedoCodexAgent` ran in the dedicated local Docker runner with
Codex CLI 0.159.2, model `gpt-6-luna`, low effort, native telemetry and native
delegation enabled. The installed image was the explicitly selected rebuilt
local digest `73ad6bbdfa6a8c14ecb50cf4276c013184b0befa75bb7facdab38977e37bd738`,
not the older default digest. It reused the existing authorized single-user
runner login volume. No credential was placed in a graph or export.

Two parent submissions and one native child completed: Fresh read exactly six
README lines, spawned one child to summarize that approved excerpt without
tools, waited for it, and returned its summary; Resume continued the same
thread without another child or tool call. Cleanup was confirmed after both
parent attempts. Live provisional agent text was observed before completion.
The short command completed between observer polls, so its output was verified
after completion; provisional command output is covered by internal tests.

The final production UI reprojected these genuine receipts. It displayed two
agent rows, parent and child turn segments, idle gaps, and the full invocation
axis. Parent first-turn input was 63,861 and child input 15,429. Child turn
output was 36. The inclusive API-equivalent estimate was $0.00320352, displayed
as $0.003204; it is not a subscription charge or invoice.

Browser checks covered paired charts, child-turn totals, exact child/thread/turn
Conversation Markdown/JSON and OpenTelemetry exports, all-activity exports,
readable six-line command output, highlighted message source, empty fuzzy-search
results with export disabled, bounded transcript scrolling, earlier-conversation
navigation and reload. Inspection submitted no model turns. Real screenshots
were captured in light/dark mode, at 1536x1150 and at a narrow 768x1050 viewport.
Private receipts and exports remain outside Git.

## Check boundaries

Dependency-light projection regressions run in the normal wheel CI suite.
Focused Langflow activity tests and frontend tests are additional local checks;
fixtures in those tests establish no provider acceptance. The pinned Langflow
overlay applied cleanly and its production build passed. The PR records actual
test counts, CI and the required independent code and visual review verdict.

The repaired first-turn baseline applies to new runner-attested fresh attempts
and observed native child creation. Legacy missing boundaries remain unknown.
Child user input is shown only if the provider actually supplied it; this run
supplied a child answer but no separate child user-message item. Multi-skill,
other models/variants and child cancellation were not exercised here. Existing
descriptive-error catalogue guards remain required; this change adds no public
error code or recovery control. No merge is authorized by this evidence.
