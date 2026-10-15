# Original-agent observability: feasibility, 2026-10-15

**Conditional go for the telemetry/data model; no-go for claiming original-runner
or graph-wide UI acceptance today.** No PR-specific agent is required. The user
selected its removal from the product.

The [prospective protocol](PROTOCOL.md) bounded this real test to three top-level
turns, read-only tools, local OTLP collection, no subagents and no GitHub writes.
The [host observation](host-observation.json) and [structural analysis](host-analysis.json)
retain source hashes and numeric/provider evidence without raw messages, commands,
outputs, login material, user identity attributes or telemetry headers.

## What ran

Docker's Linux-engine pipe was absent, even outside the sandbox. The original
`LaomedoCodexAgent` / `LocalRunner` is pinned to Codex 0.159.2 in Docker; that
runtime could not run. A separately identified real host App Server probe used
the existing installed `codex-cli 0.162.0-alpha.17.2` and normal login in place.
This is protocol/exporter feasibility, not a replacement agent or proof of the
original container boundary. A real project README was supplied read-only.

Two turns completed in one native thread. The first executed a real read-only
command with exit code 0 and observed output; the second continued the thread.
A third turn was interrupted by its exact native turn identity. The final
`thread/read(includeTurns=true)` request was refused because the thread was
ephemeral. The observation preserves this negative result as `error`; no extra
model turn or automatic retry was made. Committed event capture, not this history
lookup, must therefore retain the observed turn/message history.

## Findings

| Requirement | Real observation | Boundary |
| --- | --- | --- |
| Multiple turns | Three distinct native turn IDs; completed/completed/interrupted | Same live thread; reconnect/resume across processes not tested |
| Messages | Native `userMessage` and `agentMessage` items and assistant deltas | Private raw stream retained; no raw content committed |
| Tool calls/results | One command with arguments, output and exit code; its native item ID matches OTLP `call_id` | One command, not every tool type |
| Token series | Three updates with `last` and cumulative `total`, including cache counts | Updates are not turns; the first turn has multiple usage updates |
| OTLP | 14 actual HTTP/protobuf log/trace batches; conversation correlation observed | Local authenticated collector, not Dynatrace integration |
| Timeline spans | 1,529 spans with start/end; 1,478 parent links | Most spans are internal diagnostics; filter/roll up before UI display |
| Cost | No cost attribute observed in log attributes; spans not searched for cost | Unknown; subscription tokens do not establish an invoice amount |
| Subagents | Not executed | Provider docs support relevant structures; installed/original runtime compatibility unverified |
| Graph-run binding | Not exercised | Original host must bind graph run + node invocation to native session/turns |
| Parallel agents / Gantt UI | Not exercised | Not accepted by a one-thread protocol probe |

## Architecture implication

Keep the original Codex agent and runner. Host-owned graph execution and invocation
IDs must bind native thread/turn/item IDs and OTel trace/span IDs. Use native events
for the authoritative message/tool detail and OTLP for request/tool spans and usage.
Retain provenance and redact before any export. Do not treat all runtime spans as
agents, infer parents from overlapping clocks, or merge repeated node invocations.

The graph-wide Agents tab should select one graph execution, show agent lanes on
a shared time axis, expand turns/subagents/tools, and open rendered messages,
highlighted arguments/results and token/cost series. Use local time and duration
labels with exact UTC timestamps in tooltips. Preserve source-vs-receipt clocks.
Cost must identify provider estimate vs a rate-card estimate with model/rate/date;
missing prices and amounts stay unknown. Avoid summing cumulative counters and
avoid double-counting a model request received through both native and OTLP feeds.

The collector observed attribute names for user email/account identity and tool
arguments/output despite prompt logging being disabled. Only names and structural
metadata were committed. Product export needs explicit redaction and access policy.
`host-observation.json` keeps the initial event-name extraction (`unnamed`); the
offline analyzer resolves `event.name` and its `otel_event_counts` is authoritative.
The analyzer tries both protobuf schemas and then validates event-name or trace/
span-ID shapes; it does not identify signal type before parsing. No raw content
is exported by that analysis. The protocol was written before the probe in this
working session, but committed with the results, so Git alone cannot prove ordering.

Claude's native telemetry is source-supported by its official monitoring docs,
but no Claude instrumentation probe ran. Existing Claude reviewer calls are
reviews, not evidence of exporter or subagent observability.

## Reproduce

Requires an installed real Codex executable, existing login, Python protobuf OTLP
decoders, and explicit model-probe authorization. Never run as an unattended test:

```powershell
python probe.py --executable PATH_TO_CODEX --source PATH_TO_IMPLEMENTATION --summary host-observation.json
python analyze.py --private PRIVATE_DIRECTORY_FROM_PROBE --output host-analysis.json
```

Both files are command-line probes, not production collectors. Protobuf decoders
are optional experiment dependencies and are not required by the core wheel.

## Sources

- [Codex telemetry configuration](https://developers.openai.com/codex/config-advanced/#observability-and-telemetry)
- [Codex App Server](https://developers.openai.com/codex/app-server/)
- [Claude Code monitoring](https://code.claude.com/docs/en/monitoring-usage)
- [Dynatrace Claude example](https://github.com/dynatrace-oss/dynatrace-ai-agent-instrumentation-examples/tree/main/claude-code)

Accessed 2026-10-15. Current documentation is not proof of support in the pinned
0.159.2 Docker image. All gaps above remain gates for product acceptance.
