# Node HTTP handler ownership

This C1 checkpoint extracts the four existing loopback handlers into defining
`handler.py` modules beside their servers. Server instances own the domain service
and private bearer token; handlers use `self.server` rather than captured closure
state. Routes, CLI paths, exact body fields, body limits, response encodings,
status codes and effect-outcome classification remain unchanged.

| Owner | Handler | Request cap | HTTP-boundary failure policy |
| --- | --- | --- | --- |
| `github/issues` | `IssueRequestHandler` | 1 MiB | Existing Issue allowlist; known HTTP refusals; uncertain writes remain `issue_write_unknown` |
| `github/pull_requests` | `PullRequestHandler` | 1 MiB | Existing PR allowlist and feedback routes; uncertain writes remain `pr_write_unknown` |
| `skills/sources` | `SkillSourceRequestHandler` | 16 KiB | Existing SourceError pass-through; unknown failures become `source_unavailable` |
| `skills/operations` | `SkillOperationRequestHandler` | 4 MiB | Private parser/authorization details stay hidden behind `skill_operation_refused` |

Identical return-None redirect handlers in Skill clients, GitHub REST and Langflow
join now use `laomedo.http.redirect.NoRedirect`. That leaf imports only the
standard library. The REST consumer retains handler-class construction; other
consumers retain instance construction. SIWC and OpenCode authentication keep
their distinct redirect exceptions. The self-contained Agent and publisher
component copies are deliberate dependency/embedded-code exceptions.

## HTTP-boundary and node-visible error classification

`tests/contracts/node-http-error-boundaries.json` separates 62 HTTP-boundary
categories from 49 categories that the current node clients can export. Their
union contains 68 distinct codes, with guards against actual contracts/producers; 66
previously missing shared-catalogue entries now have explanations and recovery
matching existing controls. Existing entries and wire categories are retained.
Catalogue coverage alone does not make an HTTP category visible on the node.

The Source client collapses every HTTP error to `source_discovery_failed`; the
Operation client collapses request failures to `skill_operation_unavailable`.
Consequently SourceError categories and `skill_operation_refused` remain HTTP
diagnostics, not current Skill node output. Issue/PR clients retain only their
own `ERROR_CODES`. The Issue allowlist currently includes the four
`github_http_4xx` categories; the PR allowlist does not, and collapses those to
`github_pr_unavailable` or `pr_write_unknown` according to possible dispatch.
C1 preserves those existing differences; it does not change client projection.
Read failures and possibly dispatched writes remain distinct. Unknown-write
messages direct the user to inspect the existing result and remote resource,
and do not recommend blindly repeating a mutation.

The operation handler's `skill_request_invalid` is internal: the existing boundary
exports `skill_operation_refused`. Private service-startup validation is separate
from HTTP replies. Low-level registry, publication ingress and native transport
diagnostics not exposed by these C1 handlers retain documented catalogue coverage
gaps; this guard does not claim comprehensive coverage for those domains. Future
checkpoints must classify their public pass-through/fallback codes before moving
producers. Dynamic external failures still require safe fallback/redaction tests.

## Evidence and limits

Internal controls compare extracted handler ASTs, constructor arguments and
admission against the formatted `422887273038523ca6343234739775b1d218b673`
baseline. Reproduce the retained original source/blob contracts with:

```powershell
python tools/capture_http_handler_contracts.py --baseline 422887273038523ca6343234739775b1d218b673
```

The script reads exact Git bodies, binds only the old closure service/token and
recorded module aliases, and normalizes the class name/docstring. Its canonical
AST field representation omits only empty version-specific `type_params` metadata;
all other fields and nonempty type parameters remain significant. Unlike
`ast.dump`, it does not vary with Python's empty-field display defaults. Tests
derive the original control from its retained source on every supported Python
version before comparing the extracted handlers. Local credential-free socket controls test server-instance isolation,
authentication, redirect refusal, safe unknown failures and response categories.
The retired-import guard covers tracked Python callers throughout source,
experiments, tools, components and tests plus maintained example code exports.
Archived runtime/export exceptions require exact recorded hashes; migration
contract strings are data rather than executable imports. Four additional probe
sources are preserved byte-for-byte at this checkpoint and listed separately as
retained legacy callers, with provenance uncertainty recorded rather than a
claim that their current bytes match old seals. REST `_NoRedirect` remains an
identity alias to the canonical class for those imports. Application callers
use the canonical class; no duplicate handler or forwarding runtime exists.
No live capture or historical observation is rerun or modified.
Migration, minimal-import and structural guards protect the new owners.

These are internal controls, including existing tests named `test_live_github_*`
that use FakeGitHub. They do not establish live GitHub, Skill editing or graph
acceptance. Full Claude implementation review, installed real workflow checks
and the requesting user's final inspection remain required before merging.
Ingestion relocation (C2), interface relocation (C3), source Git consolidation
and Agent workspace changes are separate checkpoints.
