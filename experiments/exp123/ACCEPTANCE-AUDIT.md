# EXP-123 acceptance audit, 2026-10-10

This is a retrospective read-only audit of S1, not a new experiment dispatch.
The original protocol, amendment, captures and verdict are unchanged.
The merged [specification record](SPEC-EVIDENCE.md) and [S1 results](S1-RESULTS.md)
remain the evidence owners. Reproduction command, from this checkout:

```powershell
python -m unittest experiments.exp123.test_probe experiments.exp123.test_evidence -v
```

All three tests passed. They verify the 15 committed capture-file hashes,
reconstruct outcomes from the journal and frozen flows, and test negative
controls for extra invocations, wrong graph, stale head and fabricated terminal
results. No graph was dispatched, provider called, model turn used or evidence
file rewritten by this audit. This replay is not an independent fresh runtime
replication of the original seven cases.

| #123 acceptance item | Evidence and bounded disposition |
| --- | --- |
| Protocol frozen before probe | PROTOCOL.md, AMENDMENT-01.md and S1-PRE-RUN.md retain the prospective source and review order; S1 source is f5b2e9a257fe59e3f281300358d209c41546b76a |
| Duplicate, stale, failing and success events | Seven S1 cases; pending and early arrival also covered. Conflicting final observations do not overwrite a final gate |
| Checked trace/run identity | Graph, node invocation, PR/head, check, gate and delivery identities in journal; hash-checked frozen graph snapshots |
| No unexpected agent dispatch | One synthetic invocation for passing cases, two for repair/cap; stale/duplicate events and late Stop/crash deliveries do not dispatch again |
| Bounded failure loop | Unrolled two-invocation graph reaches Result2 failed after two failures; graph completion does not imply objective success |
| Independently reviewed result | Pre-run and post-run reviews on Laomedo PR #124; specification review on specs PR #300, merged as 15b147bd13ffdd244ddcc0480864ab163b61d21a |

The listed experiment acceptance is met at the amended synthetic scope. It does
not deliver the full objective of an agent publishing a PR and receiving live
GitHub feedback. Issue-state changes require separate explicit approval.

## Remaining product integration

- #104/#105 owns active-run grants, trusted staging and literal Git/gh delivery;
  do not modify that session's branch or infer acceptance from S1.
- The current gate/runtime/router/agent under experiments/exp123 are fixture
  integration code, not an installed production PR-check node. Ingress is not
  authenticated; real webhook validation, durable provider delivery identity
  and authorized PR/head ownership must be implemented and verified before use.
- Real Codex/OpenCode invocation, real PR/head changes and provider check reads
  are untested by S1. Disposable-repository acceptance needs a prospectively
  reviewed protocol and explicit write scope; model turns need a fresh cap.
- Waiting uses custom polling in one Graph.arun, not Langflow's webhook entrypoint
  or arbitrary cycles. Stop is an explicit controller cancellation, not UI Stop.
  Crash ends the old graph; it does not establish native graph checkpoint resume.
- S1 limits on per-wait deadlines, bridge egress, telemetry, unrolled cap and
  cached bytecode remain in S1-RESULTS.md. No production maturity is promoted.
