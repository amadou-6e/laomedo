# GitHub ownership

GitHub owns Issue/PR admission, selection, authorized effects and GitHub-specific
delivery policy. An Issue or PR identifies a resource and never authorizes a write.
Reusable Git mechanics have one owner, `laomedo.git`; host services own grants,
credential lookup, mediation and publication admission.

```text
github/
  contract.py                 shared repository/label admission and resource digest
  models.py                   canonical operation-intent and grant-binding records
  interface/                  public loopback HTTP adapters and trusted startup
    issues/                   client, handler, server, settings and CLI
    pull_requests/            client, handler, server, settings and CLI
  issues/                     normalized values, gateway and Issue-specific contract
    context_reader.py         read-only gh issue/timeline context
    context.py                actual read-only context CLI/main entrypoint
  pull_requests/              PR values, gateway, contract and feedback
  transport/
    mediated.py               dispatcher composing existing Git and REST paths
    git/                      GitHub branch/ref/publication policy
    rest/                     narrow GitHub REST delivery
  workflows/                  pure workflow-path classification
```

## Object and method nomenclature

| Concern / owner | Vocabulary and responsibility |
| --- | --- |
| `issues/` | `GitHubIssueGateway`: `discover`, `execute`; `GitHubIssue`: canonical normalized value. The gateway admits effects and reconciles durable outcomes. |
| `pull_requests/` | `GitHubPRGateway`: `discover`, `execute`, `prepare_feedback`, `apply_feedback`; `GitHubPullRequest`: canonical PR value. |
| `transport/` | `GitHubRestTransport`, `GitHubGitTransport`: deliver admitted operations through `__call__`; Git additionally exposes `classify_workflow_diff`. `GitHubMediatedTransport` binds matching repositories in `__init__` and forwards exact operation/binding arguments in `__call__`. |
| `interface/` | Clients are the supported app boundary. `*Server` owns endpoint lifetime/state; `*RequestHandler` owns HTTP parsing, authentication and response policy. Explicit startup CLIs compose host/domain implementations. |
| `contract.py` | `repository_from_url`, `validate_repository`, `labels_value`, `issue_digest`: independent admission/hash functions, with no I/O or authority. |
| `issues/context_reader.py` | `fetch_context`: read issue/timeline evidence and confirm issue stability; discovered PRs remain candidates. `context.main` owns arguments, JSON output and exit status. |
| `workflows/` | `touches_workflows`: pure classification, with no Git execution. |

Use `Base` only for a genuine abstract contract, meaningful adjectives for actual
variants, and a final responsibility noun. Gateway means effect admission;
Transport means delivery; a context reader performs reads. No common gateway
base, transport framework or matching folder inventory is needed. Compose the
existing Git and REST transports; keep Git mechanics outside GitHub policy.

Canonical Pydantic values stay in feature-owned `models.py`; no second record
family is added. URL admission lowercases its result; owner/name validation
preserves case and its existing argument error. The weaker historical context
dictionary stays distinct from normalized node `GitHubIssue`. The PR contract
retains its intentional `pr_digest = issue_digest` identity binding.

## Dependencies and migration

Application callers use defining modules in `interface/`; models, gateways and
contracts do not eagerly import HTTP startup, host composition or optional graph
frameworks. Shared contracts and the context reader do not depend on work_graph.
Core HTTP redirect refusal comes from `laomedo.http.redirect.NoRedirect`.

The active `python -m laomedo.github.issues.context` command keeps its parser and
`main`. Maintained imports and flat migration maps point at final definitions;
there is no retired context utility facade or duplicate dispatcher. Original
experiment sources remain byte-pinned, with explicitly selected import-only
adaptation for internal controls. Unknown external saved graphs need explicit
migration; a reference never grants authority or permission to retry unknown writes.

These ownership changes preserve payloads, argument shapes, errors, authorization
and unknown outcomes. Full code review, exact installed real-workflow validation
and owner graph approval remain pending. Internal checks and documentation are
not real graph acceptance. Leaf READMEs document the supported interfaces.
