# S12 B executable review candidate (UNEXECUTED)

The prospective `NATIVE-MANAGED-PROTOCOL.md` was committed as `e4942d2`
before this controller. Its independent design verdict permits implementation,
not execution. The verifier diagnostics received a separate bounded review;
status-write failure is deliberately fail-closed and stops its task. The
actual final executable still requires independent positive pre-run review
and green final-head CI. S12 A is consumed (see its results); no S12 B
claim/task/container/provider call has started. Amendment01 was frozen first.

Sources: `native_managed_probe.py` controller; `native_managed_worker.py`
scripted real-lease runner; `native_managed_tasks.py` exact task helpers;
`native_managed_checks.py` falsifiable assessment. Tests use mocks/synthetic
observations only, not S12 acceptance evidence. No model invocation exists.
Caller supplies fresh private root, exact final source SHA, explicit identity
approval, selected token-file reference and a private positive review record
matching identity/source. Invoke only as the module, not by path:

```text
python -m experiments.exp104.native_managed_probe --run --root <fresh-private-parent>/exp104-native-managed-s12-20261010-b --token-file <explicit-file> --source-sha <reviewed-final-head> --review-record <private-approved-record> --approval-id exp104-native-managed-s12-20261010-b
```

Both tasks use the exact invoking interpreter/checkout; an import preflight
must succeed without new installation/login fallback. Current process and
user/machine logon credential-variable names are refused, never printed or
removed. Baseline bundle size is checked before tasks/writes. Shared roots,
actual source origins, fresh lease heartbeat and verifier completed-scan
diagnostic/PID membership are checked; same-boot monotonic clocks only.

The controller refuses a baseline containing `.github/workflows`; it creates
only deterministic fixture files. This is not an attestation of repository
secrets or external hooks. The 540-second procedure deadline is checked before
every native command; commands cap at120s, API reads15s, denial20s, task helper
calls35s, readiness25s and revocation60s. An in-flight timeout preserves
uncertainty, aborts later mutations and triggers exact local cleanup. No
timeout is cancellation evidence. Cleanup can extend beyond the procedure
deadline through individually bounded ownership-checked operations.

Four intended successful provider mutations: A push/create, B push/create.
One A denied-update request follows positive saved revocation. If unexpectedly
accepted/unknown, no B create follows, keeping actual mutations bounded by
four and preserving the failure. Full provider journal includes reads; the
four-write assessment filters mutation operations and does not call that
four total requests. Direct preflight/readback reads are separately outside
the mediator journal. No remote seed writes, deletion or merge.

Any failure consumes the identity; preserve original outcome and uncertainty.
On partial setup cleanup candidates are recorded before task registration,
exact owned grants revoked, exact agent/worker/task identities removed, then
stage orphan cleanup checked with no redispatch. No broad folder deletion.
Persisted agent/stage exact-secret scan has a64MiB per-file refusal limit;
it is not a memory/process/network-exposure scan. PID/status/module-origin
checks do not prove OS token integrity, Linux/service-manager recovery,
multi-user custody, real-model Q11 or full command parity. No draft promotion
follows merely from a passing S12 result.
