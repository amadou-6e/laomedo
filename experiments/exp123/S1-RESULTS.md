# EXP-123 S1: same-graph PR-check feedback

Disposition: bounded synthetic candidate passed; product acceptance is not claimed.
Executed once on 2026-10-09 after independent pre-run approval posted on PR #124.
Source `f5b2e9a257fe59e3f281300358d209c41546b76a`, pre-run record
`029c9e0`, amendment `44a6d238`, merged governing specs
`86d6fcff5c6d51e6ad106daf59f3f7036c7f9e8b`. Protocol and source preceded
execution. No case retry, model turn, GitHub request or provider write occurred.

## Observations

| Case | Graph runs | Agent invocations | Gate results | Terminal state |
| --- | --- | --- | --- | --- |
| success | 1 | 1 | passed | completed, Result1 passed |
| early | 1 | 1 | passed | completed, Result1 passed |
| pending | 1 | 1 | passed | completed, Result1 passed |
| repair | 1 | 2 | failed, passed | completed, Result2 passed |
| cap | 1 | 2 | failed, failed | completed, Result2 failed |
| stop | 1 | 1 | none | interrupted |
| crash | 1 | 1 | none | crashed |

Every component record joins the actual Graph.run_id saved at dispatch. In
repair/cap, Router's failure selection precedes Agent2; success/early/pending
select success and reach Result1 without Agent2. The cap graph completes with
a failed result rather than claiming that its workflow objective succeeded.
An early check was retained before graph dispatch. Unknown/pending and invalid
signature did not decide a gate; duplicate/conflicting/stale fixtures did not
produce extra invocations. The Stop and crash late deliveries are explicitly
`inactive` (journal sequences 67 and 73), not merely generic refusals. Stop's
gate cancellation is recorded. Startup marks the crash case terminal without
calling arun again. Exact labelled container and volume cleanup was verified.

## Byte evidence

[observation-s1.json](observation-s1.json) is the machine-written controller
report, not primary engine output. SHA-256:
`747466ac11396d62e7e2c995f44e54fff382bd50eaf7071b5255307f778abf49`.
It carries the hashes of all 15 primary capture files under [evidence/S1](evidence/S1/):
the journal, seven raw case snapshots and seven frozen flow snapshots.
Journal SHA-256:
`ad6501e525535349f403d073350678ffb0117ce9804c7594c60ccc9fae0f7f29`.
Case rows reconstruct exactly from the captured journal. Frozen flow byte
hashes match each graph_started record. `test_evidence.py` verifies committed
bytes and applies the frozen assessment without executing a graph or writing
observations. All captured files were scanned for credential markers and host
paths; only synthetic fixtures, component code and generated IDs are retained.

## Deviations and limits

- As the pre-run reviewer noted, the 25-second controller deadline is per wait,
  not total case duration; the crash health wait permits 90 seconds. Gate waits
  are bounded at 12 seconds. No deadline triggered in this run.
- The custom wait components poll a synthetic ingress. The conditional cap is
  unrolled into two distinct agent vertices. This proves a viable integration
  on pinned Langflow/lfx 1.12.3, not native webhook waiting or arbitrary cycles.
- Stop is the explicit controller endpoint cancelling the existing arun task,
  not a click on Langflow's UI Stop. Crash handling is the integration's terminal
  startup sweep, not resumed Langflow execution.
- The worker had default bridge outbound access, a loopback-published port and
  no credentials. Langflow telemetry was not explicitly disabled. The source
  directory was mounted read-only, including any cached bytecode; the pinned
  image used Python 3.14, unlike the local test Python 3.12.
- Flow JSON was captured after Graph.from_payload, so it may contain mutations
  of the original construction payload. It is nevertheless hashed before arun
  and captured unchanged. Synthetic node ingress is not authenticated; no
  production ingress security claim follows.
- No real agent commits, reads/corrects a PR, or consumes GitHub events here.
  Those remain separate active-run mediation and ingress acceptance work.
