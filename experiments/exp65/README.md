# EXP-65: post-408 job lookup and late effect

Issue: https://github.com/amadou-6e/laomedo/issues/65. This bounded follow-up
to EXP-10 asks whether the v2 job ID remains a useful read-only source of
partial execution state after the synchronous route returns `408`.

The [protocol](PROTOCOL.md) and [amendment](AMENDMENT-01.md) were committed
before their respective runs. The first run's observation is retained in Git
history at `95e991b` (all four status reads returned 500, but the capture did
not retain the distinguishing error code). The amended replication's current
[observation](observation.json) was written directly by the committed probe.

## Observed result

With Langflow 1.12.3 pinned by image digest and a verified 3-second server
timeout, one v2 invocation returned `408 EXECUTION_TIMEOUT` with a job ID at
3.031 seconds. All four read-only GETs at 0, 1, 4 and 7 seconds after that
response returned `500 JOB_FAILED`, including the first GET **before** the
synthetic effect. The endpoint performed its single recorded effect about
3 seconds after the 408, then wrote its response. The job's 500 had no
durable `error_detail` in the response. Host/container clock calibration was
about 0.03 seconds with about 0.05 seconds uncertainty per reading, much less
than the late-effect interval.

This is a negative first-slice result: a terminal Langflow job state does not
account for the later external effect. It must not be mapped to confirmed
cancellation or complete IF-06/07 evidence. The probe did **not** capture a
Laomedo run trace or execute a real Codex worker. No job was polled through
another endpoint and no timed-out POST was retried. The disposable container
and volume were removed after each run.

## Verification

`python -m unittest experiments.exp65.test_probe -v` checks the pinned result
and rejects an omitted effect, a fabricated safe status and a fabricated
pre-timeout effect. The main Laomedo test suite runs separately. The current
observation and source hashes are pinned in the paired specs evidence record.
