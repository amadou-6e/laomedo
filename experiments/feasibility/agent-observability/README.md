# Graph-wide agent observability feasibility

The bounded real host App Server probe observed three turns on one native
thread: two completed and one interrupted. It captured one command with its
result, three usage updates and native/OTLP tool identity correlation. The
[frozen protocol](PROTOCOL.md), [observation](host-observation.json) and
[analysis](host-analysis.json) distinguish observations from remaining gates.
Raw prompts, tool outputs and private login state are not published.

The host ran Codex 0.162.0-alpha.17.2. The existing Docker runner pins 0.159.2;
Docker was unavailable, so these results do not verify the original runner,
graph-run/invocation binding or a graph-wide UI. There is no new agent node.
Subagent hierarchy, Claude capture and provider-reported cost remain unverified.
Token counters are not invoice amounts. Trace parent IDs do not prove an agent
hierarchy. OTLP log protobuf source timestamps were absent; log `event.timestamp`
attributes, timed spans and receipt times must be distinguished. The final
`thread/read(includeTurns=true)` request failed for the ephemeral thread, so
the probe exited with code 1 without a history export. Streaming receipts had
already captured the three turns; no model turn was repeated.

The probe exhausted its three-turn cap. Do not rerun model-backed probes without
new authorization. The retained historical activity modal is unwired preparation.
