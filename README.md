# laomedo
Design, inspect, and experiment with Codex and Claude Code agent workflows

The [issue 119 feasibility experiments](experiments/feasibility/119/README.md)
cover no-model Codex skill discovery, a manifest pilot, and a bounded
credential-backed skill turn. Discovery and manifest checks use disposable
fixtures without a credential. The completed turn and its remaining limits
are documented in the experiment README.

The [issue 120 runner isolation probes](experiments/feasibility/120/README.md)
build no-model checks for model/effort validation, private profile isolation,
thread persistence, and a guarded stream-events probe. All four no-model
probes run without a credential; the stream probe requires one and stops
before any model call if unavailable.
