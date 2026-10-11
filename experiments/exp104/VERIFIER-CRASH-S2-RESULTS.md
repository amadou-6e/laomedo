# Verifier worker loss S2 result

Executed once after independent pre-run approval at clean exact source
`21d66f97a7971ff1926e19b825645a1a5ee2f0e2`, on 2026-10-09. Original
protocol froze at `648164a` before probe implementation; Amendment 01 disclosed
synchronous cleanup deadlines; Amendment 02 at `e3671af` froze fresh S2 after
the failed consumed S1. LF resource staging repair was `adcb3ae`. No S1
effect or identity was retried.

The machine-generated observation is copied unchanged into
`VERIFIER-CRASH-S2-OBSERVATION.json`, SHA-256
`9e6bd8f8ad1d3b895cc5e284e55af7e23ac9a88f6d785a22053e690577d78bf8`.
It holds fixture/commit/source hashes, stage ID/state and outcome booleans,
not user paths, credentials, container ownership token or raw logs.

## Observed

- The real credential-free worker reached the deliberately instrumented
  pre-export pause. Its ownership reservation existed before the kill.
- After the exact worker-tree kill, the Docker stage remained owned. One
  restarted production scan reported verified orphan removal; the same
  stage was absent afterward.
- Restart dispatched no verification. The original verification stayed
  unknown and the persistent one-shot claim remained.
- The separately named same-prefix control remained running through that
  cleanup; final exact-owned cleanup removed it too. Both cleanup flags true.
- Declared scope is zero model turns, grants or provider operations. No real
  GitHub credential/path was supplied; the diagnostic used only local Git and
  Docker. No independent network capture was made.

## Assessment and limits

Pass for cleanup-only restart after this instrumented worker loss. The source
shows reservation before Docker create; runtime observation proves reservation
presence at kill, not an independently measured pre-create timestamp. Captured
stage ID/state are evidence, not an independently captured label/name audit.
No Docker client was active at the pause, so late creation after a pre-readiness
kill is not proven by this case (synthetic controls remain narrower).

This is not safe cleanup while every manager is down, power loss, scheduler
recovery, real agent/grant/GitHub behavior or full #97/#105/Q11 acceptance.
The S1 pre-pause failure remains historical. Both source and result require
their scoped independent review; no full-draft merge is justified by this row.
