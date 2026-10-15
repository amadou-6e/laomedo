# Graph-wide agent observability feasibility protocol

Frozen before execution, 2026-10-15. User authorizes real feasibility verification
and review; this probe does not change the application or any GitHub resource.

The original `LaomedoCodexAgent` uses `LocalRunner` / Codex App Server, pinned to
CLI 0.159.2 in Docker. First check Docker. If unavailable, report original-runner
integration as blocked. A separately identified host App Server probe may test
protocol/OTLP feasibility, but cannot establish original-container acceptance.
Do not introduce another agent node or substitute fixtures as a deliverable.

Use the installed host Codex executable, record its actual version, normal
existing subscription login in place, and a private temporary evidence directory.
Bind an OTLP HTTP/protobuf receiver only to 127.0.0.1, with a per-probe bearer
header. No remote telemetry service, credential export or profile copy.
Read-only sandbox, approval never, no subagents, no GitHub writes, no file changes
by the agent. Source is the real implementation README in a separate read-only
probe directory. Never collect unrelated personal sessions or transcripts.

Maximum three top-level model turns, each at most 90 seconds. Turn 1 asks for
one read-only README tool call. Turn 2 continues the same native thread without
tools. Turn 3 is interrupted using the native turn identity. Stop on an uncertain
model-start outcome; never automatically repeat an uncertain turn. No provider
model or effort override. Shut down the owned process after the final attempt
and permit OTLP exporter flush before stopping the receiver.

Capture native JSON-RPC requests/receipts and actual OTLP logs/traces privately.
Track process exit, source/receipt timestamps, thread/turn/item IDs and exact
configured runtime. Publish only a structural summary, numeric usage counters,
event-type/attribute names, source hashes and uncertainty; never raw prompts,
messages, tool outputs, auth headers or local login state.

Assess independently: multiple distinct turns on one session; user/assistant
message availability; actual tool arguments/results and item identity; incremental
and cumulative token usage; OTLP delivery and native-session correlation; native
interruption; recorded parent/subagent identifiers; provider-reported cost.
Missing cost is unknown. Never derive invoice amounts from subscription usage.
Subagent hierarchy and Claude telemetry may be source-supported but remain
unverified without an actual authorized, bounded provider execution.

The Gantt view is feasible only with graph-run / invocation binding from the
original host, native source start/end intervals (or explicitly receipt-based
intervals), and observed parent relationships. Host protocol evidence cannot
establish that graph binding, multi-agent parallel capture, or UI acceptance.
