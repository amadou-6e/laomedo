# EXP-07: independent orphan lease supervisor

This zero-model harness tests the selected independent stage lease supervisor
plus backend startup sweep with a disposable HTTP external-write canary. The
user-selected maximum tolerated exposure window is 60 seconds. Reproduce the
bounded probe with `python experiments/exp07/probe.py --max-exposure-seconds 60`.
The 2026-10-02 observation passed: the disposable grant ended within 0.600
seconds and the worker was observed stopped within 1.208 seconds. Three test
writes were accepted after kill was requested and before revocation. A later
write returned 403. On restart the synthetic run was `crashed`, with one
dispatch attempt and incomplete evidence. The probe removed its named Docker
resources; the remaining resource-name check found none.

`probe.py` starts pinned Langflow, a separate synthetic worker, an independent
host supervisor, and a canary service on a private Docker network. The worker
repeatedly makes test-only external writes with a random grant. The canary
enforces grant expiry independently and records every write, renewal and
revoke. The supervisor renews while the backend is alive; after backend death
it revokes the grant and kills the worker. A restarted backend sweeps the
durable synthetic run to `crashed` without redispatch. The probe compares
observed grant and worker lifetime upper bounds against the selected window.

Only named EXP-07 Docker resources are created and removed. No production
repository, personal credential, Git push or model turn is used. The test
stage is launched by the harness, not by a production Langflow adapter, so
the result must be interpreted as an orphan-control mechanism probe. In
particular it does not prove that a real push credential or every network lane
obeys the same grant, or that a production Langflow adapter launches and stops
stages through this supervisor.
