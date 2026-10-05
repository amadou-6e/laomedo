# EXP-66: live synthetic timeout-to-trace integration

[Issue #66](https://github.com/amadou-6e/laomedo/issues/66) tests the
[proposed reconciliation contract](https://github.com/amadou-6e/specs/pull/213)
against pinned Langflow 1.12.3. The [protocol](PROTOCOL.md) was committed
before the first call. Its [amendment](AMENDMENT-01.md) was committed before
one diagnostic replication to retain a hash-verifiable runner source row.

The first `observation.json` at `19f823d` is historical: it observed the
same outcome but omitted part of the runner journal row used to calculate
the effect receipt's source hash. The current `observation.json` is the
direct capture from the amended run; `tests/test_exp66_probe.py` checks it
and uses mutations that must fail.

In the amended run, one v2 call returned `408 EXECUTION_TIMEOUT` with a job
ID at 3.015 seconds. Four read-only polls returned `500 JOB_FAILED`, including
polls both before and after the delayed synthetic effect. Laomedo's durable
trace retained the timeout, all four native status deliveries and the effect
under one pre-dispatch invocation identity. After reopening the SQLite store,
the trace still reported `timed_out`, `partial`, one dispatch attempt and
uncertain action uniqueness. It did not claim cancellation or completion.

This is a synthetic, zero-model integration check, **not** evidence that a
real Codex worker can be cancelled. The runner and its effect were disposable;
the container, named volume, temporary SQLite store and synthetic token were
removed after capture. Real-agent behavior and the first-slice timeout gate
remain open under [issue #22](https://github.com/amadou-6e/laomedo/issues/22).
