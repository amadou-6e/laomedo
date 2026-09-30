# laomedo
Design, inspect, and experiment with Codex and Claude Code agent workflows

The [issue 119 feasibility experiments](experiments/feasibility/119/README.md)
cover no-model Codex skill discovery, a manifest pilot, and a bounded
credential-backed skill turn. Discovery and manifest checks use disposable
fixtures without a credential. The completed turn and its remaining limits
are documented in the experiment README.

The [issue 120 runner isolation probes](experiments/feasibility/120/README.md)
add no-model checks for model/effort dispatch and profile isolation, plus
bounded ChatGPT-backed tests of resume and streamed events. The temporary
private login handoff is for single-user local feasibility only.

The [issue 123 trace spike](experiments/feasibility/123/README.md) checks a
synthetic private Codex rollout against AGENTVIZ's parser and tests a minimal
event projection without additional model calls. Claude and full Langflow
correlation remain unverified.
