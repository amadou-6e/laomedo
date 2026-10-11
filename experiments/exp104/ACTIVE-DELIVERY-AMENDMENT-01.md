# Prospective synthetic issuer/host-thread boundary

Recorded before this probe's first execution or pre-run approval. The fixed
active-delivery protocol remains historical and this is an explicit refinement:
the controller directly issues a synthetic connection-bound grant in the real
MediationStore; the active run record's supervised ownership is a fixture, not
evidence of production approval/LeaseClient supervision. Mediator HTTP server
and BundleVerifier run in probe-owned threads, not separately managed tasks.
No real credential is loaded. Production authority issuance, lease loss and
Task Scheduler lifecycle are separate evidence and not accepted by this case.

The test still requires the real agent-side mediation client, frozen-byte
Git-object verifier, verified-stage policy gate, exact-commit Git transport
with disclosed local-remote rewrite, and REST transport with a fake opener.
This narrower local integration proves composition, not the full production
authorization/liveness chain. Review current cleanup for both the agent and
any verifier stage before execution; failure must remain visible and one-shot.
