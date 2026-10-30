# GitHub ownership

GitHub owns Issue/PR admission, selection, authorized effects and GitHub-specific
REST/Git delivery policy. Reusable Git mechanics belong to `laomedo.git`; grants,
credential lookup and host mediation remain with their existing host owners.
An Issue or PR value identifies a resource and never authorizes a write.

## Earlier handler checkpoint

The C1 design separates each existing loopback server from its module-level
request handler and shares identical redirect refusal through the dependency-free
`laomedo.http.redirect.NoRedirect`. The Issue/PR wire contracts,
wire schemas, error categories and effect reconciliation remain unchanged.
Implementation and internal checks do not establish real graph acceptance.

| Concern | Owner | Object/function vocabulary |
| --- | --- | --- |
| Issue behavior | `issues/` | `GitHubIssueGateway`, `GitHubIssue`; discover, execute, normalize |
| PR behavior and feedback | `pull_requests/` | `GitHubPRGateway`, `GitHubPullRequest`; discover, execute, prepare_feedback, apply_feedback |
| Native delivery | `transport/` | `GitHubRestTransport`, `GitHubGitTransport`, `GitHubMediatedTransport`; transport already-admitted operations |
| Workflow path policy | `workflows/` | `touches_workflows`; pure classification, no Git execution |
| Public HTTP adapters | `interface/issues/`, `interface/pull_requests/` | `*Server` owns lifetime/state; `*Handler` owns HTTP parsing and response policy |

Use `Base` only for a genuine abstract contract, a meaningful adjective for an
actual variant, and a final responsibility noun. Do not add a common gateway
base or identical folder contents merely for symmetry. Canonical Pydantic data
stays in its existing feature `models.py`; no parallel record family is added.

The `interface/` boundary has the same meaning as Agent interface: the public
contracts and concrete adapters the rest of the app uses. C2 publication-ingress
relocation is separate; registry, source Git and workspace changes remain later
checkpoints.


## C3 public interface design

The `interface/` boundary contains the existing HTTP adapters:
clients, handlers, servers, feature-local Settings and trusted startup CLIs.
Its README and per-feature READMEs define the object/method vocabulary before
implementation. Domain models, gateways/services and immutable persistence remain
under their existing owners; no common handler base or forwarding layer is added.
Application callers use defining modules in interface; only explicit CLI startup
loads host/native composition. Source-domain fixed policy remains source-owned.
Current checkpoint status and migration constraints are in `interface/README.md`.
