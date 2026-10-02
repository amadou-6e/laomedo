# laomedo
Design, inspect, and experiment with Codex and Claude Code agent workflows

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
