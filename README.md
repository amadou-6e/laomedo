# laomedo
Design, inspect, and experiment with Codex and Claude Code agent workflows

The [issue 119 feasibility experiments](experiments/feasibility/119/README.md)
cover no-model Codex skill discovery, a manifest pilot, and a bounded
credential-backed skill turn. Discovery and manifest checks use disposable
fixtures without a credential. The completed turn and its remaining limits
are documented in the experiment README.

The [issue 120 runner isolation probes](experiments/feasibility/120/README.md)
add no-model checks for model/effort dispatch and profile isolation, plus
bounded ChatGPT-backed tests of native resume and streamed tool events.

The [issue 122 Skill Draft proof](experiments/feasibility/122/README.md)
records versioned editing rules, deterministic draft guards, and the current
agent-tool blocker. The [local skill core](laomedo/README.md) implements
immutable revisions and human-reviewed draft promotion without depending on
that blocked agent-edit path.
