# Credential-free imported workgraph demo

The export composes the production Skill Reference, Codex Agent and Output
Contract components in Langflow 1.12.3. Fixture issue ingestion calls the existing
issue-context parser through an injected fixture transport. It never invokes
`gh`, authenticates a provider, runs a model or contacts GitHub.

Issue ingestion and the pinned Skill Reference feed the Codex Agent. A
requirements-only Output Contract feeds the agent precheck input; another
instance with the identical form validates the structured submission downstream.
Two instances keep the graph acyclic. Conditional routing stops the inactive
branches using Langflow's graph mechanism. The success destination creates only
a **simulated** draft PR reference. Failure, rejection and recovery destinations preserve
the validation record, run and trace references without publication.

Routing precedence is rejection for an invalid form; recovery for an accepted
form with a non-completed executor, incomplete/unknown evidence, or unknown task
outcome; success for an accepted complete execution reporting success; and task
failure only for an accepted complete execution explicitly reporting failure.
The runtime-interruption fixture submits a valid success form with a partial
report, so acceptance plus the recovery route tests execution state independently
of form rejection. It must retain the exact run/trace identity and clamp the
reported success to an unknown outcome without publication.

`fixtures.json` and `expectations.json` are frozen inputs and handwritten expected
routes. `flow.json` embeds the actual component code and port metadata. Tests
deserialize that committed export and call `Graph.from_payload(...).arun()`;
they do not call the router directly or reimplement graph execution.

Run in the installed pinned image, from this repository in PowerShell:

```powershell
$image = 'langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0'
docker run --rm --pull=never --network none --mount "type=bind,source=$PWD,target=/workspace" -w /workspace -e PYTHONPATH=/workspace --entrypoint /app/.venv/bin/python $image examples/langflow-workgraph-demo/build_flow.py
docker run --rm --pull=never --network none --mount "type=bind,source=$PWD,target=/workspace,readonly" -w /workspace -e PYTHONPATH=/workspace --entrypoint /app/.venv/bin/python $image -m unittest discover -s tests/langflow -p test_workgraph_demo.py
$sourceCommit = git rev-parse HEAD
docker run --rm --pull=never --network none --mount "type=bind,source=$PWD,target=/workspace" -w /workspace -e PYTHONPATH=/workspace -e "LAOMEDO_DEMO_SOURCE_COMMIT=$sourceCommit" --entrypoint /app/.venv/bin/python $image examples/langflow-workgraph-demo/acceptance.py
```

The acceptance script writes `evidence.json` with observed routes, source/image
pins and hashes of the committed inputs. The fixture runner scripts rejected and
corrected submissions through the real shared evaluator and records zero or one
scripted continuation. This proves graph wiring and outcome propagation; it
does **not** establish that a live model used the native precheck tool or corrected
itself. Native dynamic-tool protocol tests belong to #135. No claim is made that
this fake runner preserved physical files during interruption; the graph retains
the supplied partial-evidence references. A live Codex run and verified real
draft PR remain separate gates under #138 and #139.
The evidence field `scripted_continuations` is fixture configuration, not an
observed native continuation count. Ledger reservation and actual continuation
budget enforcement are tested under #135, not established by this fixture.
An additional negative control edits only the downstream form in the imported
graph; the source requirements stay pinned and the resulting mismatch must reject.

The evidence amendments incorporate #135's reviewed continuation and precheck
preservation fixes and the review's distinct recovery route, valid interrupted
form, explicit scripted-count label and downstream-form drift negative control.
The protocol and expectations are committed before the amended export is frozen
and the six cases rerun. The original evidence remains in Git history at
`cd4201c`; the current evidence names the amended frozen source. Native runner
responses do not yet establish `evidence_complete=true`, so the live publication
gate remains unresolved under #139. This demo's explicit fixture value must not
be taken as evidence that the live gate already passes.

For interactive inspection, import `flow.json` into the pinned Langflow editor.
The exported runner URL is a loopback fixture endpoint, not a live configured
service. Do not point the demo at a real runner and treat simulated publication
as production acceptance.
