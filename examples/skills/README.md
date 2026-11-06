# Skills

Select and inspect an immutable Skill, then build one graph where the existing
Agent proposes an atomic multi-file edit. The host validates the proposal and
records a candidate revision with parent history and per-file comparisons.
The source and canonical latest do not change automatically.

Follow the [Skill walkthrough](../../docs/features/skills/walkthrough.md) for
private registry, edit-policy, runner and source/history service setup. Import
the actual `editor-skill/` instruction bundle and retain its exact revision.
Use the pinned Langflow environment and the installed Laomedo package.

From the repository root:

```powershell
python examples/skills/build_flow.py `
  --skill-id $skillId --revision $revision `
  --editor-revision $editorRevision --runner-url $runnerUrl `
  --edit-request $editRequest --output $privateFlowPath
```

For a subsequent candidate also pass `--commit-id $baseCommit`. An empty base
commit is valid at the imported root only. Supply real immutable references;
credentials, transport tokens and edit tickets never belong in the saved graph.
The command writes and validates a graph. It does not start an Agent or apply an
edit. Inspect it in the app before explicitly running against your local services.
After execution, inspect the connected Task output for the completed operation
receipt, then the selected file's history/diff. Langflow builds connected outputs;
the unused Operation Result port is not built automatically in this graph. Inspect
the receipt before leaving the page: output inspectors are transient, while the
registry history persists. An uncertain apply reply needs history reconciliation,
not blind graph retry.

`build_flow.py` constructs the workflow. [`../graph.py`](../graph.py) owns only `node()` and `edge()`:
they read actual component metadata and construct native graph handles without
loading an experimental provider or running a campaign. The caller supplies
component paths, values and connections; graph identity and port semantics remain
those of the existing example. No new service or provider abstraction is introduced.

[Original campaigns and limitations](https://github.com/amadou-6e/laomedo/tree/1d3c2aa2d2e93222eac558091a5846c68fc33cec/archives/examples/skill-operations)
are preserved byte-for-byte with provenance on `exp`. Those records establish
their named historical executions, not acceptance of a fresh run. Promotion, Git
publication and the pending Skills-source hardening are separate concerns.
