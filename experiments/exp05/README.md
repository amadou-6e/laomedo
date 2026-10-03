# EXP-05: synthetic invocation identity and partial-event crash windows

This is a zero-model experiment for [issue #35](https://github.com/amadou-6e/laomedo/issues/35).
It uses the merged EXP-04 `WorkflowRunStore` for run/trace reservation and
`evidence.py` for a separate synthetic invocation, native-session receipt,
raw-event receipt, and derived projection. It does not dispatch Codex, Claude,
or Langflow.

Run:

```text
python experiments/exp05/probe.py
python -m unittest tests.test_exp05_evidence
```

The probe kills a child process before invocation reservation, after
reservation, after dispatch but before native-ID receipt, after the native ID,
after raw event flush, and after projection. A normal completion is the control.
The sanitized [observation](observation.json) records each process exit, durable
run/invocation identities, native ID if known, raw receipts, projections, and
post-restart state. A startup sweep marks unfinished invocations and runs
`crashed`; it projects only committed raw receipts and never redispatches.

| Kill boundary | Recoverable invocation | Native ID | Raw/projection after restart | Evidence state |
| --- | --- | --- | --- | --- |
| Before invocation reserve | No | No | 0 / 0 | Run `crashed`; invocation not invented |
| After reserve | Yes | Unknown | 0 / 0 | `crashed`, `unknown` |
| After dispatch, before native ID | Yes | Unknown | 0 / 0 | `crashed`, `unknown` |
| After native-ID receipt | Yes | Known | 0 / 0 | `crashed`, `unknown` |
| After raw-event flush | Yes | Known | 1 / 1 | `crashed`, `partial` |
| After projection | Yes | Known | 1 / 1 | `crashed`, `partial` |
| Normal control | Yes | Known | 1 / 1 | `completed`, `complete` |

The event-flush row has no projection **before** restart; startup derives its
single projection from the committed raw receipt. Receipt sequence correlates
raw and projected records, but it is not a producer-stable deduplication key.
An absent source event ID remains absent. EXP-09 / issue #39 must select and test
the replay policy; this probe neither deduplicates redelivery nor proves a
complete provider event stream. It also does not test host power loss, real
native-session APIs, full-backend lifecycle, or same-turn recovery.
