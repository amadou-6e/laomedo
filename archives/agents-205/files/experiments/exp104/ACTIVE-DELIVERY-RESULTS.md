# No-model active-container delivery S1

One execution of `exp104-delivery-s1-20261009`, independently approved before
execution at source `f9705522a2a2804943b4c262c1d9c306f6e3029b`. Protocol
`9ae2878`, Amendment01 `dd4e675` and Amendment02 `174b183` preceded execution.
The machine-produced observation is committed unchanged as
[ACTIVE-DELIVERY-OBSERVATION.json](ACTIVE-DELIVERY-OBSERVATION.json), SHA-256
`2c649c2d3d3eb0f178c261d7146b721973a353305c0e9266a8131f7e9c10bef8`.

Result: passed within this local integration scope. The real mediation client
inside a still-owned, still-running scripted container froze the handoff;
production Docker Git-object verification and the verified-stage policy gate
preceded the exact-commit push by code requirement and fixture-reported order
(no host verification timestamp is captured). Host-observed refspec is
`ce3a7c7713803b77b9e7b32efa4b8cccd531cadc:refs/heads/run-branch`.

Host-observed fake REST order is POST, GET, GET, GET, PATCH, GET, GET on the
declared PR paths: create, bound read, stale correction preflight, valid
correction preflight, correction, authoritative readback, final agent read.
The final body hash and local bare remote ref matched the fixture result while
its container was still alive. The fixture-reported operations separately show
the stale correction rejected and unbound PR read denied; they are not raw
provider evidence. No mutation was retried after uncertainty.

Host controls require specific refusal codes: completed push
`push_stage_unverified`, replaced connection `connection_unavailable`, revoked
grant `grant_unavailable`. Completed freeze requires direct freezer
`run_grant_mismatch`, no new attempt, and retains mediator `unknown` rather
than calling it confirmed rejection. Provider call count did not change.
Both agent and verifier cleanup were verified; the saved stage report and
probe-side absence check agreed after the verifier thread finished. The fixture's
`denied` label denotes an error response, not a distinct mediator state.

## Limits

Zero model turns and zero real-provider calls are declared by this harness.
REST uses an injected fake opener; Git transport rewrites exactly the declared
remote to a local bare repository. This is not live GitHub acceptance or literal
`gh` parity. Grant issuance and supervised ownership are synthetic fixtures;
host services are probe-owned threads, not managed tasks. Bridge networking
permits egress, so no network-isolation claim is made. The credential stayed
host-side by mount design; this case does not independently inspect every
process environment. No real runner-loss/lease outage, all-manager outage,
scheduled task lifecycle or native-agent judgment is established. Draft
#97/#105, #100/#104 and wider gates remain open.
