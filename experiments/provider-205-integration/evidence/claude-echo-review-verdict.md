# Claude native-echo fix (fd34cb7e → ae56d802)

**Bottom line:** the fix is correct and has no blockers. Native user echoes stay in the raw evidence but no longer show up as a Claude answer, and every other branch of `_native_event` behaves as before.

## How the change interacts with the existing code

I read all of `claude-echo.diff`, `agent.py:835-990`, and every use of `_last_streamed_text`.

- **Raw evidence is kept.** Every admitted event is appended to `raw-events.jsonl` (lines 842-843) before any branch runs, so the echo stays in the raw log. The new test checks this as the final raw receipt.
- **Tool calls in user messages still complete.** The `tool_use` and `tool_result` branches (lines 862-894) come before the new guard. Because the guard's `continue` skips only the current block, a `tool_result` carried in a user message still completes its tool call, including the Skill use evidence.
- **Only assistant text is displayed.** Text and thinking blocks are now emitted only when `event.type == "assistant"` and `message.role` is `"assistant"` or missing. The default only matters inside assistant events, so the guard can't let a user event through. There is no filtering based on the content of the text.
- **The streamed-text marker is no longer overwritten.** `_last_streamed_text` is now set only from assistant text, here (line 906) and when a streamed block completes (line 984). That matters at finalization (line 1189), which emits a fallback answer only when the last streamed text differs from the final answer. Before the fix, a late user echo overwrote the marker, so the real answer would have been emitted a second time. The fix closes that duplicate too, and the test asserts the marker stays "marker reply".
- **Other paths are unaffected.** Partial stream events (line 944 onward) are a separate path that carries only assistant blocks. The deduplication of streamed text and native receipts is unchanged, and the marker is still reset at each host turn (line 1095).
- **Remaining assumption (low):** any other wrapper event type that carries text blocks is now ignored for display. The Claude event types handled here (`system`, `assistant`, `user`, `stream_event`, `result`) don't carry assistant text outside `assistant`, so I see no lost output. The live fresh/resume run you reported, with its display types, is consistent with this. That run is your evidence, not something I checked.

## Test and docs

- **Regression test:** it puts the host prompt first, then an assistant answer, then a late user echo, and checks that exactly one `userMessage` and one `agentMessage` are displayed, that the streamed-text marker is unchanged, and that the raw echo is kept.
- **README:** the five added lines match the behaviour.

## Image inspected

**`claude-clean-activity-redacted.png`** (773×714): the OpenTelemetry rows 5–8 end with `user_prompt / log` and sit above Conversation. Conversation shows "2 of 2", a "You 02:18:18 PM" bubble, a "Claude 02:18:20 PM · 0.0s" reply, and then the footer. There is no extra Claude row. The message bodies are masked, so I can't judge their content; the image is the standalone render, not the owner's browser.

## Verdicts

- **Code and docs:** APPROVE.
- **Visual:** APPROVE, limited to the masked standalone render: one user row and one assistant row, no echo bubble, consistent layout.
- **Relied on your statements:** the test runs, Black, CI, the live run and the owner's browser screenshot.
- **Not covered:** cancellation and abrupt-recovery acceptance, old pre-fix Activity entries (left as they were), and footer licensing L-01 (separate scope).
- **Not authorized:** merge or issue closure.