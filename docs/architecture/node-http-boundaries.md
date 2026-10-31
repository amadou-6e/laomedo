# Node HTTP handler ownership

The four loopback APIs define their request handlers in
`handler.py` modules beside their servers. Server instances own the domain service
and private bearer token; handlers use `self.server` rather than captured closure
state. Routes, CLI paths, exact body fields, body limits, response encodings,
status codes and effect-outcome classification remain unchanged.

| Owner | Handler | Request cap | HTTP-boundary failure policy |
| --- | --- | --- | --- |
| `github/interface/issues` | `IssueRequestHandler` | 1 MiB | Issue allowlist; known HTTP refusals; uncertain writes remain `issue_write_unknown` |
| `github/interface/pull_requests` | `PullRequestHandler` | 1 MiB | PR allowlist and feedback routes; uncertain writes remain `pr_write_unknown` |
| `skills/interface/sources` | `SkillSourceRequestHandler` | 16 KiB | SourceError pass-through; unknown failures become `source_unavailable` |
| `skills/interface/operations` | `SkillOperationRequestHandler` | 4 MiB | Private parser/authorization details stay hidden behind `skill_operation_refused` |

Identical return-None redirect handlers in Skill clients, GitHub REST and Langflow
join use `laomedo.http.redirect.NoRedirect`. That leaf imports only the
standard library. The REST consumer retains handler-class construction; other
consumers retain instance construction. SIWC and OpenCode authentication keep
their distinct redirect exceptions. The self-contained Agent and publisher
component copies are deliberate dependency/embedded-code exceptions.

## HTTP-boundary and node-visible error classification

`tests/contracts/node-http-error-boundaries.json` separates HTTP-boundary
categories from categories the node clients can export. Guards compare this
inventory to actual contracts/producers and require descriptive catalogue entries
and recovery matching existing controls.
Catalogue coverage alone does not make an HTTP category visible on the node.

The Source client forwards only the exact bounded
`repository_cleanup_unverified` category; other HTTP errors collapse to
`source_discovery_failed`. The
Operation client collapses request failures to `skill_operation_unavailable`.
Consequently other SourceError categories and `skill_operation_refused` remain HTTP
diagnostics, not current Skill node output. Issue/PR clients retain only their
own `ERROR_CODES`. The Issue allowlist currently includes the four
`github_http_4xx` categories; the PR allowlist does not, and collapses those to
`github_pr_unavailable` or `pr_write_unknown` according to possible dispatch.
These allowlists are intentionally distinct.
Read failures and possibly dispatched writes remain distinct. Unknown-write
messages direct the user to inspect the existing result and remote resource,
and do not recommend blindly repeating a mutation.

The operation handler's `skill_request_invalid` is internal: the existing boundary
exports `skill_operation_refused`. Private service-startup validation is separate
from HTTP replies. Low-level registry, publication ingress and native transport
diagnostics not exposed by these handlers retain documented catalogue coverage
gaps; this guard does not claim comprehensive coverage for those domains. Future
changes must classify public pass-through/fallback codes before changing
producers. Dynamic external failures require safe fallback/redaction tests.

## Evidence and limits

Local credential-free socket controls test server-instance isolation,
authentication, redirect refusal, safe unknown failures and response categories.
The retired-import guard covers tracked Python callers throughout source,
experiments, tools, components and tests plus maintained example code exports.
Archived runtime/export exceptions require exact recorded hashes; migration
contract strings are data rather than executable imports. Four probe
sources are preserved byte-for-byte and listed separately as
retained legacy callers, with provenance uncertainty recorded rather than a
claim that their current bytes match old seals. Selected internal probe controls
use explicit import-only migration; application callers import the canonical
class. REST exposes no private redirect compatibility alias.
No live capture or historical observation is rerun or modified.
Migration, minimal-import and structural guards protect defining owners.
Maintained example components follow their canonical source files. A single
current masked-graph contract protects every other graph value without chaining
intermediate source revisions or embedding old implementations.

These are internal controls, including existing tests named `test_live_github_*`
that use FakeGitHub. They do not establish live GitHub, Skill editing or graph
acceptance. Full Claude implementation review, installed real workflow checks
and the requesting user's final inspection remain required before merging.
