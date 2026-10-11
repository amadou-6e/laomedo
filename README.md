# laomedo
Design, inspect, and experiment with Codex and Claude Code agent workflows

The [Work Graph foundation](docs/work-graph.md) imports GitHub work and native
blocker relationships using an existing `gh` login. It stores verified,
immutable snapshots and inspects filtered projections with dependency
readiness calculated from the full graph. This slice provides a Python
service and CLI; the graph UI is a subsequent slice.

The [local Langflow skill-agent pilot](examples/skill-agent-pilot/README.md)
builds a persistent single-user Codex runner on the existing Docker boundary,
pins a whole-skill revision, and supplies a saved Langflow flow. Its default
turn cap is zero until a bounded model-backed test is authorized.

The [issue 119 feasibility experiments](experiments/feasibility/119/README.md)
cover no-model Codex skill discovery, a manifest pilot, and a bounded
credential-backed skill turn. Discovery and manifest checks use disposable
fixtures without a credential. The completed turn and its remaining limits
are documented in the experiment README.

The [issue 120 runner isolation probes](experiments/feasibility/120/README.md)
add no-model checks for model/effort dispatch and profile isolation, plus a
bounded private ChatGPT handoff for thread resume and streamed events. The
three-turn spike reported a no-go for the proposed local MVP on its evidence.

The [issue 122 Skill Draft proof](experiments/feasibility/122/README.md)
records versioned editing rules, deterministic draft guards, agent edits, and
native resume. The [local skill core](laomedo/README.md) implements immutable
revisions and human-reviewed draft promotion separately from agent execution.

The [issue 121 Claude probes](experiments/feasibility/121/README.md) pin the
Claude Agent SDK and guard isolation, settings, streaming, and resume tests.
No Claude model call ran: the native CLI and dedicated credential were
unavailable, so Claude capability remains unknown and the local MVP is no-go
on current evidence.

The [issue 123 trace spike](experiments/feasibility/123/README.md) checks a
synthetic private Codex rollout against AGENTVIZ's parser and tests a minimal
event projection without additional model calls. Claude and full Langflow
correlation remain unverified.

### Trusted draft publisher (#138)

`components/laomedo/pr_publisher.py` requests downstream draft publication after
Output Contract acceptance. It sends only an empty authenticated runner POST;
the host recomputes validation from its own frozen output. Graph data never
contains the GitHub token or controls a grant, branch, deadline or PR payload.

The opt-in host `PublicationController` is injected into `LocalRunner`, not
automatically enabled by the CLI. It requires a finite explicit lifetime, the
existing mediator store, an independently started lease service, a private
verified-artifact resolver, a PR description builder, provider transport and
provider readback. Its startup `recover()` sweep is called only after the old
controller is known dead. Do not install a resolver that trusts graph data.
An exact verified push receipt must exist before handoff; this publisher does
not push or capture an agent checkout after validation.

The existing supervised grant remains active through validation. Agent bearer
operations end at handoff; expiry, cancellation and uncertain effects revoke
the same grant, and unknown outcomes are never resent. Every PR is forced draft
with a stable marker and a journaled effect identity before dispatch. Readback
checks the exact head commit, branch, base, draft flag, title and body. A remote
effect already in flight cannot be undone by cancellation.

Credential-free tests use fake provider receipts and cleanup callbacks, not
real GitHub access or a model. The real runner's evidence completeness still
remains unknown, so its output cannot pass the trusted publication gate. Live
acceptance remains under #139, including #100 and the recorded #104 gate,
provider/precheck acceptance, a separately approved turn cap and scoped identity.
No running configuration is activated by these changes.
