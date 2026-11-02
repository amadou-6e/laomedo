# Prospective network and cleanup/control corrections

Recorded before the first execution of `exp104-delivery-s1-20261009`.
The container uses Docker Desktop's bridge network to reach the host mediator.
This permits general egress: this case does not prove network isolation.
No real provider request is authorized; injected REST and Git connectors limit
all provider operations to the in-process fake and local bare Git remote.

Cleanup must capture both the agent and every durable verifier ownership record,
and refuse a cleanup pass if the verifier thread is still live. Negative controls
must check their specific refusal codes. Completed-run freeze returns `unknown`
at the mediator boundary; separately check the freezer's `run_grant_mismatch`
and the absence of a new attempt, not a confirmed refusal claim from `unknown`.
Restore a current connection before the revoked-grant control and use a complete,
otherwise valid fresh update payload. Confirm Node exists in the pinned image
before execution. Mount a bounded writable temporary filesystem for the fixture.
