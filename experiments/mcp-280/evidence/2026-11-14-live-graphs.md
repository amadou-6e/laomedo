# MCP #280 real graph validation, 2026-11-14

Implementation: `amadou-6e/laomedo`, branch `feat/280`, head `ead50c23`;
intended base `feadd5fbccdebbe7bf1d5614c5bad187b9ad975d`.
The isolated services loaded the HTTP discriminator correction before its
commit; launcher metadata can therefore still name preceding head `9809025b`.
This is real integration evidence, not a fixture test or a merge approval.

## Fresh execution

Each provider passed over both HTTP and STDIO: Codex, Claude and OpenCode.
Every case registered a native Langflow MCP server, selected only `read_marker`,
connected the native Toolset output to the Agent MCP Tools input, and submitted
the graph through the app session API. Each completed with one selected upstream
call, zero unselected calls, one manifest tool, and the correct random marker.
The marker was absent from the prompt; a private counter confirmed upstream use.

## Resume

Each provider passed a STDIO graph with fresh and resume Agent nodes sharing the
MCP Toolset. Each completed with two selected calls, zero unselected calls, the
correct marker, two execution attempts and a native session reference present.
The harness did not independently compare the two native session identifiers.

## In-flight cancellation

Each provider entered the selected STDIO tool once before cancellation was sent.
All three reached cancelled status with zero completed tool calls observed and zero
unselected calls. Codex category was `cancelled_by_user`, Claude category was
`claude_cancelled`; OpenCode reported no error category. No result was delivered
before cancellation. The upstream outcome after the observation is unknown.
These checks establish observed runner cancellation after dispatch; they do not
prove arbitrary upstream tool side effects can be rolled back.

An earlier harness attempt omitted the cancel API's required empty JSON body.
It failed request validation, was corrected, and is excluded from these results.

## Rendered graph

The owner-shared VS Code integrated browser displayed the actual Codex STDIO
graph. READ_MARKER was selected and the Toolset edge reached Agent MCP Tools.
Skill References remained a distinct input above MCP Tools. A dedicated
`mcp-280.localhost` host resolved cookie collisions between independent local
app instances on the same `127.0.0.1` hostname. The screenshot contains no auth
error. Browser visibility is transient: a shared tab can later be backgrounded.

## Limits and review

Actual rendered screenshot and sanitized logs are in ignored local review
evidence; private profiles, markers, server configuration, credentials and raw
agent history are not published. HTTP acceptance server processes end after
their checks, so completed HTTP graph links are not reusable demonstrations.
STDIO graphs retain their app-owned server configuration for owner inspection.

The HTTP discriminator correction received focused Claude APPROVE. Full PR
own-diff review remains incomplete. Claude accepted the single static render and
confirmed the bounded evidence claims. The logs do not independently establish
source-byte provenance, live lease revocation or upstream termination. Multiple
servers plus Skill References coexistence was initially outside this matrix;
the subsequent checks below cover it. Required CI passed at `ead50c23`; specification PR #419 remains
open and dependent on its ACP specification branch. No merge is authorized.

## Subsequent composition and cancellation audit

Codex, Claude and OpenCode each completed a real STDIO graph containing two native
MCP server nodes and one pinned Skill Reference. Each returned the marker with
exactly one selected upstream call per server, two manifest tools and zero
unselected calls. This establishes coexistence of connected Skill and MCP inputs;
it does not prove the model read or followed the Skill text. Two earlier Codex
attempts were refused before dispatch because the harness supplied a Skill
frontmatter name differing from its registered ID. Correcting that test input
resolved the refusal, without production changes.

All three providers then passed another in-flight STDIO cancellation check with
a live capability audit. The harness retained the private scoped capability in
memory while the run was active. After terminal cancellation it verified both
that the rendezvous file was removed and that an authenticated GET using that
same old capability returned 403 `mcp_registration_unavailable`. Each captured
one capability and passed both assertions. No capability was printed or saved
as evidence. These are cancellation revocation checks, not app-shutdown or
completion revocation checks.

Claude reviewed every own-diff hunk across bounded packets against the stated
base/head, including the corrected nonempty catalogue diff. Code coverage is
closed with low advisories; overall PR approval remains incomplete for live
privacy/shutdown and UI interaction evidence and the specification dependency.
The new composition and revocation evidence awaits independent recheck.

## Completion and targeted privacy audit

All three providers completed another real HTTP graph, returned the correct
marker with one selected call and no unselected calls, and passed the same live
revocation audit after completion. Each removed its grant file and refused the
previously valid capability with 403 `mcp_registration_unavailable`.

The harness compared the actual captured scoped capability and the isolated
runner API token, in memory, against five blobs per provider: the graph export
plus existing durable record/activity/attempt/diagnostic JSON or JSONL files.
Neither value appeared. This is a targeted known-secret scan, not proof about
every possible credential or every private diagnostic writer. The acceptance
upstream servers have no real upstream credentials. Native private config is
deliberately outside these public/durable projection checks.

Separate sanitized inspection of completed two-server records confirmed one
retained Skill receipt in each provider's `skills` collection. This establishes
materialization evidence rather than proof of model compliance with instructions.

App-shutdown behavior, broader deployment reachability, provenance comparisons,
status/cancel with dead native upstreams and editor interactions remain separate
acceptance gaps. Existing controlled native transport/graph tests cover some of
these invariants but are not substituted for live provider acceptance.
