# EXP-104 protocol amendment 01 — authorization and service-failure controls

Status: frozen **before the first live run**. The original
[LIVE-PROTOCOL.md](LIVE-PROTOCOL.md) is unchanged. This amendment responds to
the posted reviews on Laomedo #103 and #105; it does not turn developmental
tests into campaign evidence.

1. **Separate lifetimes.** The credential-owning mediator must run in a
   process separate from the independent lease service, sharing only their
   protected grant ledger. Killing the lease service must leave the mediator
   running, or the expiry test is vacuous. Capture distinct PIDs and process
   parents before any kill. No ambient host `gh` identity is allowed.
2. **Hard-kill the lease service without restarting it.** After one last
   recorded renewal, terminate only the exact lease-service PID. Using a
   synthetic, non-GitHub transport, attempt a distinct harmless write with A
   and B at approximately 0, 15, 30, 45 and 60 seconds after the last
   renewal, stopping each run's attempts once denied. Record the authorization
   result and provider-call count. No real GitHub mutation is repeated for
   this timing test. Both grants must be denied no later than 60 seconds from
   their last renewal, despite the mediator staying up. Record any backwards
   wall-clock step; if detected, the result is inconclusive.
3. **Authorization negatives.** Before the real write, demonstrate denial
   before transport for: a PR update of a number not bound to the run; a
   GraphQL mutation labelled read; a REST non-GET labelled read; and a Git
   push whose *trusted diff classifier* finds `.github/workflows/` even though
   the caller's `workflow_file_change` flag is absent or false. A missing or
   uncertain diff classifier must also deny the push. Preserve the fake
   transport's call log as the negative control.
4. **Provider credential after the probe.** Record how the dedicated App
   installation token or fine-grained token is revoked or expires after the
   run, including mediator-crash behavior. Its lifetime is distinct from the
   run grant's ≤60-second lifetime. Do not commit or print token bytes or a
   token hash. If revocation is not available, wait for expiry and report the
   residual window; do not claim immediate credential revocation.
5. **Known limits.** A request already in flight when revocation occurs may
   still complete. Record dispatch time and any late effect separately. The
   measured guarantee is that *new* dispatches are denied after revocation or
   expiry. The tests must not use the broad personal `gh` login, and the live
   part remains blocked until a dedicated scoped identity and reviewed
   transport exist.
