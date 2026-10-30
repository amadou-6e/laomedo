# Native GitHub mediation after ACP

Status: assessment only; production mailbox relay is **NOT IMPLEMENTED** here.
Repair remains [issue #215](https://github.com/amadou-6e/laomedo/issues/215),
separate from [ACP PR #214](https://github.com/amadou-6e/laomedo/pull/214).

ACP provides one Agent session/turn protocol. It does not grant network access
to native commands, authenticate GitHub operations or replace the host effect
journal. Completing an Agent turn therefore does not prove its requested GitHub
operation happened.

## Observed failure and limits

The retained real check at `4eb5d95` launched an Actions-read-only command through
Codex ACP. The command exited 2 with `mediation request failed`; the host journal
recorded zero provider attempts. A separate credential-free container on the
controller bridge reached the actual mediator health endpoint with HTTP 200.
This distinguishes runner completion and bridge reachability from native-command
success. The inner sandbox's networking policy is the leading explanation;
the precise failing syscall was not observed. Do not present it as a confirmed
root cause. Current PR/issue metadata inspected on 2026-10-30 still tracks the
repair separately; neither is evidence of a production fix.

## Proposed ownership

Retain native command networking restrictions. A command writes a bounded request
to a run-owned file mailbox. A trusted relay outside that command sandbox sends
it to the existing host mediator. The mediator remains the sole owner of GitHub
credentials, operation/repository grants, instance checks, expiry, effect
identity and remote-write reconciliation. The Agent gets neither GitHub login
material nor the relay's run capability. ACP remains the session protocol;
the mailbox is a native tool boundary, not a fourth Agent protocol.

`experiments/exp139` supplies an experimental client/relay, not a production
package or accepted workflow. Preserve its fixed destination, atomic publication,
bounded regular-file requests, configured mediator destination and existing
run authorization. Do not copy its experiment request-count or lifetime caps
into normal runners. Production resource limits must bound queue/file/process
use while respecting the actual run lifecycle.

Before promotion, decide and review relay process identity and isolation: the
experimental same-UID process is not an established production boundary. Cover
symlink/reparse/link substitution, bounded responses, abandoned requests, relay
readiness/death, cancellation, durable replay/idempotency and ambiguous remote
writes. Keep mailbox/capability paths out of snapshots, bundles, Activity and
logs; remove only exact owned resources. A dead relay or timed-out write must
never trigger a blind second remote operation.

## Required acceptance for the separate increment

- First use a fixed no-model native-sandbox probe to distinguish denied command
  networking, unavailable relay and unreachable mediator without credentials
  in output.
- Perform one real read-only Actions request. Require the expected host provider
  attempt and agreement with independent host readback; an Agent answer or
  completed run alone cannot pass.
- Independently confirm direct native access to mediator, unrelated host
  services and external networking remains denied.
- Reject wrong repository, ungranted operation, altered/missing capability,
  stale instance, expired grant and unauthorized replay before an effect.
- Exercise oversized request/response, exhausted queue, relay death and cancel.
  Preserve descriptive shared error codes, safe recovery and uncertain-write
  reconciliation.
- Verify actual runner cleanup and absence of private mailbox/capability data
  from exported files and retained observability. Internal controls cannot
  substitute for these real paths.

Continue this work in a dedicated PR against #215 after reviewing that boundary.
No relay activation, new network allowance, GitHub write or mediation success is
part of the structured-data refactor.
