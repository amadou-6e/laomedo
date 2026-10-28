# laomedo
Compose and inspect agent work with versioned Skills and GitHub issue/PR context.

## Start here

- [Who Laomedo is for](docs/vision-and-goals/README.md#who-this-is-for): workflow
  authors, Skill maintainers and developers working with repository tasks.
- [Getting started](docs/getting-started.md): install the local app, configure a
  real Claude runner, run your first project question, inspect its answer and clean up.
- Practical guides: [Agents](docs/features/agents/walkthrough.md),
  [Skills](docs/features/skills/walkthrough.md),
  [Issues](docs/features/github/issues/walkthrough.md) and
  [pull requests](docs/features/github/pull-requests/walkthrough.md).

Browse the [implementation documentation](docs/README.md) for vision, architecture
and feature guides.

## Source layout

Install this checkout with `python -m pip install -e .` (or install its wheel).
For Codex Docker runners (normal and split), install `python -m pip install -e '.[runner]'`
in the Python environment used by its launcher, or use `uv sync --extra runner`.
The optional extra currently pins the py-docker jobs feature revision for the
pre-PyPI local trial; core/Langflow installations do not need it. See the
[trial setup and recovery](docs/architecture/docker-runtime-adoption.md#local-installation-and-recovery).
Python implementation lives in `src/laomedo`; `agents` owns execution, with
`skills`, `github`, `host`, `activity`, `integrations/langflow` and `work_graph`
providing the other domains. Components, frontend, tests and docs remain at the
repository root. See [package layout and migration](docs/architecture/package-layout.md).
Imports and service commands use their owning domain modules. Older saved
graphs and launchers have an explicit one-time migration; forwarding modules
and the checkout-only import bridge are removed.

## Historical investigation records

These investigations describe their original revisions and availability limits.
Use the current guides above for setup; historical campaign budgets do not limit
normal user runs.

The [agent observability feasibility study](experiments/feasibility/agent-observability/README.md)
assesses native App Server events and OpenTelemetry for the original Codex agent.
The [current activity guide](docs/features/agents/activity.md) describes retained
Agent conversations and provider-specific limits separately from that earlier study.

The [Work Graph foundation](docs/architecture/work-graph.md) imports GitHub work and native
blocker relationships using an existing `gh` login. It stores verified,
immutable snapshots and inspects filtered projections with dependency
readiness calculated from the full graph. This slice provides a Python
service and CLI; the graph UI is a subsequent slice.

The [local Langflow skill-agent pilot](examples/skill-agent-pilot/README.md)
builds a persistent single-user Codex runner on the existing Docker boundary,
pins a whole-skill revision, and supplies a saved Langflow flow. Its default
runner has no global verification turn cap. Bounded experiments must enforce
their allowance in a separate harness, never in the normal service.

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
native resume. The [local skill core](docs/features/skills/registry.md) implements immutable
revisions and human-reviewed draft promotion separately from agent execution.

The [issue 121 Claude probes](experiments/feasibility/121/README.md) pin the
Claude Agent SDK and guard isolation, settings, streaming, and resume tests.
No Claude model call ran: the native CLI and dedicated credential were
unavailable, so Claude capability remains unknown and the local MVP is no-go
on that campaign's evidence. Current Claude setup is documented in
[getting started](docs/getting-started.md) and [the Docker guide](docker/claude/README.md).

The [issue 123 trace spike](experiments/feasibility/123/README.md) checks a
synthetic private Codex rollout against AGENTVIZ's parser and tests a minimal
event projection without additional model calls. Claude and full Langflow
correlation remain unverified.

## Integration and validation references

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
real GitHub access or a model. The native execution closure described below
can establish evidence availability; live acceptance remains unverified. Live
acceptance remains under #139, including #100 and the recorded #104 gate,
provider/precheck acceptance, a separately approved turn cap and scoped identity.
No running configuration is activated by these changes.
### Native execution evidence closure

For supervised Codex invocations, the host can close the retained native trace
after confirmed reader shutdown, exact executor cleanup and a ready snapshot.
The check binds this invocation's terminal turns and tool/item lifetimes, checks
command completion and the retained final answer, and records only sanitized
reason/count diagnostics. Missing or ambiguous evidence remains `unknown`.
`completion_basis: native_trace_closure` establishes retained execution evidence,
not truthful task success or a successful remote write. Resumed invocations must
establish their own closure. Live provider and imported publisher acceptance are
still part of #139; no running configuration is changed by this implementation.

Only the supervised lease path can close evidence. Resumed invocations remain
unknown and cannot publish cumulative changes until every contributing attempt
has a durable closure record; that history is outside this preparation's scope.

### One downstream Output Contract

See [the simplified imported demo](examples/langflow-contract-routing/README.md).
A single downstream form supplies Codex precheck expectations automatically,
then validates and routes its output. Legacy explicit-precheck graphs remain
compatible. Credential-free imported-graph evidence does not establish a new
live publication run.

### Linked-source Skill selection

The Langflow Skill node can discover skills from a repository URL or an explicitly
allowed local source, then filter Skill and Revision dropdowns by typing. Each
selection resolves to an immutable registry bundle for the existing runner and
read-only file viewer. Old exact references remain compatible. See the
[overlay and source service guide](frontend/langflow-skill-viewer/README.md#linked-source-selector-157)
and its separately gated activation draft. The initial Git route supports public
GitHub/GitLab repository roots; private Git authentication is not implemented.

### Live GitHub Issue component

The [GitHub Issue node](examples/github-issue/README.md) discovers repository
labels and issues, filters by all selected labels, reads current content and
accepts incoming close/modify operations through existing scoped mediation.
Credentials stay on the host. A read-only activation draft and fake-provider
browser/native checks are included; the old FrozenIssue experiment is separate.
