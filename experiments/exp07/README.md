# EXP-07: independent orphan lease supervisor

This zero-model harness tests the selected independent stage lease supervisor
plus backend startup sweep with a disposable HTTP external-write canary. The
numeric maximum tolerated exposure window is supplied as
`--max-exposure-seconds` only after user selection. No #37 pass/fail execution
has occurred yet.

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
the result must be interpreted as an orphan-control mechanism probe.
