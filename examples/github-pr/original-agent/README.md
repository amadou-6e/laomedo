# Original Codex Agent PR feedback

The real two-node [graph](flow.json) ran **GitHub PR Task → existing
LaomedoCodexAgent → the same PR Operation**, using Docker LocalRunner and Codex
0.159.2. On [PR #22](https://github.com/ga84jog/laomedo-exp104-disposable-20261007/pull/22),
one Agent invocation and one confirmed host intent set the title to
`Original Codex Agent feedback verified`. Independent GitHub readback matched;
the description stayed unchanged. Replaying the same ticket returned the stored
outcome without a new model call or observed PR change. See [evidence](evidence.json).

A separate real graph cancellation acknowledged native interruption, retained no
host write intent, left the PR unchanged and verified container removal. See
[cancellation evidence](cancellation-evidence.json). The campaign exhausted its
three-turn cap. No further model-backed verification is authorized by this
protocol; do not reset its ledger or automatically retry an uncertain outcome.

The earlier PR #21 trial completed a confirmed description write, but the model
failed its preservation instruction despite receiving the context and reading
the skill. It is a task-quality failure, not successful preserve/append evidence.
The prospective [protocol](PROTOCOL.md) records the correction before turn 2.
No live provider-unknown write was deliberately induced; those controls remain
internal tests. Passing mediation does not establish the quality of every model
proposal or eliminate prompt injection risk within the granted content scope.

## Host configuration

Import `title-skill/` as the immutable `pr-feedback-title` skill using SkillStore,
then use its actual revision. Run the independent lease service and existing
LocalRunner, with private state/registry, an inspected immutable image and the
dedicated authorized local credential volume. [Docker startup](../../../docs/docker-sandbox.md)
documents the checked profile and preflight. Provider tokens must stay outside
all Agent mounts; this example reuses the existing test-only Codex login volume.

The GitHub PR host needs an existing exact-target grant binding and a private
`--feedback-bindings` JSON map from `repository#PR` to that host-owned reference.
The normal mediation grant limit stays 60 seconds. A trusted lease owner may
renew a still-live grant for a bounded invocation; a ticket never renews it.
Revoke on host shutdown. The live campaign used bounded host renewal and revoked
its grants on completion. This is a trusted single-user connection, with general
owner/flow binding still unfinished.

The backend's `prepare-feedback` call reserves identity before model dispatch.
Only the backend holds its five-minute ticket. The Agent returns an action and
changes, never an authority field. `apply-feedback` validates the original grant
binding, target and digest, stamps the envelope and invokes existing mediation.
Model-authored identity/target fields, expired tickets, revoked or rebound grants
and changed PR content are refused. Ticket expiry also uses the monotonic clock.

`build_flow.py --repository OWNER/REPO --number NUMBER --title TITLE --revision
sha256:HASH --runner-url http://127.0.0.1:PORT --output PATH` exports the same
topology without executing it. Set private `LANGFLOW_CONFIG_DIR` and
`LANGFLOW_DATABASE_URL` before using standalone lfx. Backend environment config
supplies `LAOMEDO_RUNNER_TOKEN_FILE`, `LAOMEDO_GITHUB_PR_URL` and
`LAOMEDO_GITHUB_PR_TOKEN_FILE`; no credential or grant enters the export.

The saved live graph records ephemeral loopback service ports from the verified
run. Those test services have stopped and the grants were revoked. Reconfigure
trusted services and obtain a newly bounded run before execution; importing the
graph does not grant access or start a provider. Cancellation uses a separate
invocation, and its ticket never reaches write mediation.
