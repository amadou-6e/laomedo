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

## D4 shared contracts and delivery ownership

PROPOSED / NOT IMPLEMENTED in this README-first checkpoint: move the existing
repository URL, label and canonical resource-digest functions to `contract.py`.
Move the existing case-preserving `validate_repository` from work_graph into that
same dependency-light owner. URL admission still lowercases its result; owner/name
validation still preserves case and its existing argument error. These are distinct
contracts. Issue/PR response and patch admission remain feature-owned.

The read-only `gh` reader belongs in `issues/context_reader.py`; the active
`python -m laomedo.github.issues.context` CLI keeps its actual parser and `main`.
Its weaker historical context dictionary is intentionally separate from the
normalized node `GitHubIssue` model. No new schema or authorization is introduced.

`transport/mediated.py` owns `GitHubMediatedTransport`, which composes the existing
Git and REST transports and forwards admitted operation/binding arguments. GitHub
Git publication policy stays in `transport/git/`; reusable Git execution stays in
`laomedo.git`. There is no abstract gateway, transport framework or forwarding API.

| Name | Meaning and interface vocabulary |
| --- | --- |
| `repository_from_url`, `validate_repository` | Admit the existing URL or owner/name form without merging their different normalization/error rules. |
| `labels_value`, `issue_digest` | Preserve exact label admission and canonical JSON hashing; the historical digest name remains supported. |
| `fetch_context` | Read and confirm issue text, discover timeline PR candidates, and preserve incomplete/unknown results. |
| `GitHubMediatedTransport` | Compose Git/REST routing through `__init__` and `__call__`; select no new identity or authority. |

Names retain the existing noun vocabulary: Gateway admits effects; Transport
delivers an admitted operation; a context reader performs reads. `Base` is reserved
for a real abstract extension contract. This move needs no new base or variant.
Public HTTP adapters remain discoverable under `interface/`; core contracts do not
import host composition, work_graph or optional graph frameworks.

All maintained callers and flat migration maps move to defining symbols. The PR
contract keeps its intentional `pr_digest = issue_digest` identity binding. Retained
experiment sources remain byte-pinned, with explicit import-only adaptation for
internal controls; they are not executed as live verification or silently rewritten.
Unknown external saved graphs remain an explicit migration constraint. Code moves
preserve errors, payloads, callable signatures, authorization and unknown outcomes.
