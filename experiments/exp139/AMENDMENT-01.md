# EXP-139 prospective authorization and case allocation

2026-10-11, before any live acceptance call. Extends PROTOCOL.md; no earlier
negative result is changed. Native closure is merged in Laomedo `da7504d` under
specs `b038ddac20846c6d5ad56097828892c5dc8815ea`.

The owner approved four submitted model turns, including timeouts, and one
draft PR in `ga84jog/laomedo-exp104-disposable-20261007`, using the host-only
`.env` reference `GH_LAOMEDO`. Existing Codex subscription login custody remains
the bounded local runner profile; no API credential is substituted. No new
grant from another experiment is reused. Exact configuration approval remains
required before launching services or executing this graph.

Allocate the cap as follows:

1. Success plus same-request precheck correction: one submitted turn, one
   mediated push to a new experiment branch and one downstream draft PR.
2. Reported failure: one submitted turn, no GitHub grant or write.
3. Downstream rejection: one submitted turn with valid precheck output but a
   deliberately changed downstream form. Pin mismatch must reject, no write.
4. One spare turn, unused unless a prospectively recorded and reviewed recovery
   is safe. It is not permission to repeat an uncertain GitHub operation.

The third case tests contract pin rejection, not exhaustion of a continuation
retry. Retry exhaustion and interrupted execution remain credential-free
controls; any unexecuted live case is recorded explicitly. Graph node retries
remain one, with the existing prohibition on continuation after unverified
side effects. The campaign uses the runner's durable turn ledger and never
resets it. A failed or unknown success case stops external writes.

Read-only input preparation may freeze one existing issue from the approved
repository and obtain its baseline Git objects before the acceptance manifest.
These are host reads, not model submissions or acceptance writes; record them
separately. This does not authorize creating or editing an issue. The bounded
task creates a report identifying that frozen issue, rather than implementing
arbitrary instructions found in its body.
