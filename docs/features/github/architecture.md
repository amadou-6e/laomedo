# GitHub architecture

The [Issue component](../../../components/laomedo/github_issue.py) and
[PR component](../../../components/laomedo/github_pr.py) own graph selection
and operation inputs. `src/laomedo/github/issues/` and `pull_requests/` own
their respective contracts, clients, gateways and service boundaries.
Shared transport code lives under `src/laomedo/github/transport/`.

The trusted host owns credentials and mediation authority. Agent-proposed
operations must pass host validation before a remote write; an uncertain outcome
is distinct from confirmed success and must not be blindly resent. See
[mediated commands](../agents/mediation/commands.md) and
[host services](../agents/mediation/host-services.md).

The [Issue guide](../../../examples/github-issue/README.md) describes discovery
and operation results. The [PR guide](../../../examples/github-pr/README.md)
describes returning an Agent operation to the same selected PR node. Provider
execution remains an [Agent](../agents/README.md) concern.
