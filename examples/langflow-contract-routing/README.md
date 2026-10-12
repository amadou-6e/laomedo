# Single downstream Output Contract

Import `flow.json` into pinned Langflow1.12.3 with the Laomedo package installed.
The visible graph is Issue + Skill → Codex → Output Contract → one destination.
Only four contract ports are shown: Success, Failure, Rejection and Recovery.
The Codex adapter reads and freezes the directly downstream static form before
sending its request, supplying the native precheck without a backwards edge.

This demo uses fixture issue data and simulated publication. No model calls or
GitHub writes are performed by its tests; an actual execution still requires a
configured runner. Do not use the old live experiment's consumed grant/budget.
Legacy demonstration exports and frozen EXP139 evidence retain their separate
identities. Current legacy examples refresh embedded component source while
preserving old explicit requirements/validation connections and routing.

The four integrated routes use adapter-retained runner execution metadata.
Incomplete/unknown execution or evidence selects Recovery even for absent or
malformed output. Completed evidence with invalid output selects Rejection;
valid reported success/failure selects the corresponding path. Unselected
branches are stopped using native Langflow outputs. Existing legacy validation
routing keeps its historical rejection-first behavior.

Automatic binding is Codex-only. One directly connected static form is supported;
multiple contracts/agent sources, dynamic form inputs and conflicting explicit
pins refuse. A form edit after freezing cannot replace the agent's expectations.
The local adapter record is not attestation against custom Python code; external
publication remains independently verified by the host.

Verification: run `python -m unittest discover -s tests/langflow` inside the
pinned network-disabled image with PYTHONPATH=/workspace and the repository
mounted at /workspace. Binding unit tests also run with
`python -m unittest discover -s tests -p test_contract_graph.py`.
