# EXP-04: durable identity before synthetic dispatch

`workflow_run_store.py` writes an immutable launch record to a private SQLite
database with `synchronous=FULL` before a callback can run. It records the run
and trace IDs, exact graph bytes/hash, component source hashes, resolved config
bytes/ref and trigger. A conservative attempt is committed before callback.
Restart sweep marks unfinished runs `crashed` and never replays them.

Run `python experiments/exp04/probe.py` to spawn six crash phases in separate
temporary databases. The [observation](observation.json) includes the persisted
rows, monotonic synthetic callback count, and restart status. An attempt may
exist without a callback, and a callback may run without a completion. Both
are deliberately treated as uncertain effects.

Run `python -m unittest tests.test_workflow_run_store` for invalid input,
dispatch refusal, one-attempt and sweep checks. This is a zero-model local
prototype. It does not yet wire the live Langflow adapter or the real runner;
[#22](https://github.com/amadou-6e/laomedo/issues/22) owns early real-run
identity and cancellation integration.
