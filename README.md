# laomedo
Design, inspect, and experiment with Codex and Claude Code agent workflows

The [issue 119 feasibility experiments](experiments/feasibility/119/README.md)
cover no-model Codex skill discovery, a manifest pilot, and a bounded
credential-backed skill turn. Discovery and manifest checks use disposable
fixtures without a credential. The completed turn and its remaining limits
are documented in the experiment README.

The [issue 120 runner isolation probes](experiments/feasibility/120/README.md)
add no-model checks for model/effort dispatch and profile isolation, plus two
credential-gated probes for thread resume and streamed tool events. The two
credential-gated probes accept only a dedicated API-key credential and stop
before any model call otherwise.
