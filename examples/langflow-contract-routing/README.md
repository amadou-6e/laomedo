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

## Explicit migration of original two-port exports

Original saved exports retain their embedded code and execute, but the editor
matches their old class name to the new catalog entry, relabels the two ports
Success/Failure and shows an update banner. Do not accept that update: the new
four-route class does not provide the original Requirements/Validation handles.
Use the explicit offline migration before editing old flows. In the pinned
Langflow runtime with this checkout on PYTHONPATH, run:

```powershell
python examples/langflow-contract-routing/migrate_legacy.py original.json migrated.json
```

Import `migrated.json` separately. This command never overwrites its input or an
existing output, accepts only the known original two-port source, and preserves
node IDs, configured values, positions, edge IDs and port names. Only the class
and its outgoing handle type change to `LaomedoOutputContractLegacy`. Unknown
modified code refuses; inspect and migrate custom variants manually. This is
not automatic graph migration and does not change frozen historical evidence.

The known-source comparison is strict: unexpected line endings or customized
code may refuse migration rather than silently change an unknown component.
Encoded edge handles are checked against their structured values; only their
data type changes. Generated node IDs and port names remain unchanged.

## Provider-neutral template refresh

Current Agent templates use the shared provider-neutral component and refreshed
Langflow metadata. Graph/node identities, connections and configured values are
retained. These refreshed exports were loaded for structural validation; they
were not rerun against a model/provider. Earlier execution receipts remain
historical. The pre-refactor exports are retained at Git revision
`735e4171266bd47afe56f685d93f2faba1c885f2`.
