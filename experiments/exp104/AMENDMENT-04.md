# EXP-104 amendment 04: selected connection and credential generation

Status: frozen before any live #104 run. The original
[`LIVE-PROTOCOL.md`](LIVE-PROTOCOL.md) and synthetic amendments/results remain
unchanged. This amendment adds the account-connection decision merged in
specs #254 (`9c287ec`) and the clarification proposed in specs #256. A live
run waits until #256 is reviewed and merged, and pins that exact merge SHA.

## Added preflight

The disposable identity must be connected **explicitly** to the broker as a
selected GitHub connection. Browser sign-in is the product default, but a
new, repository-scoped token deliberately supplied for this bounded test is
allowed. The connection record supplies a non-secret `connection_id`, owner,
repository and credential generation; the run approval and durable mediator
grant persist that exact ID/generation before dispatch. The stage gets only
its run capability. Do not use or fall back to the host `gh` login, Git
Credential Manager, `GH_TOKEN`, Git config or an agent-mounted reusable token.

Before a live effect, verify that the trusted approval owner confirms the
connection's user/repository and that the credential-owning transport resolves
the same generation. If no production connection registry and secret store
exist, stop: the synthetic #108 broker is not a substitute. Record only a
non-secret source reference and permissions, never token bytes or hashes.

## Added negative control

After admitting run A, rotate or disconnect its selected connection before
one new uniquely identified, harmless effect. The mediator must refuse it
before provider transport; an unrelated run B on a separate still-current
connection must remain usable. Keep this separate from the original
runner-loss case and distinguish a pre-dispatch refusal from an effect already
in flight. If the outcome of any earlier write is uncertain, do not retry it.

The original exact-runner-loss, 60-second bound, real Git push/read-back,
provider-call count, and no-cleanup-without-authorization acceptance rules
remain mandatory. This amendment does not itself authorize a live credential,
select a credential source, or turn synthetic evidence into a pass.
