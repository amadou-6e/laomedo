# Issue 119: no-model Codex discovery probe

This directory contains a synthetic, disposable probe for the first part of
[specs issue #119](https://github.com/amadou-6e/specs/issues/119). It starts
`codex app-server`, calls `initialize` and `skills/list`, and stops. It never
starts a thread or model turn. It does not need a credential.

## Reproduce

Requirements: Python 3.9 or newer and a Codex CLI binary. The observed run used
Python 3.12 and `codex-cli 0.155.0-alpha.16.3` on Windows. From the Laomedo
repository root:

```powershell
python experiments/feasibility/119/probe_codex_discovery.py --codex '<absolute-path-to-codex.exe>'
```

The script constructs a child environment with separate `HOME`, `USERPROFILE`,
and `CODEX_HOME` values. It creates three synthetic skills in temporary roots:
one at `<project>/.agents/skills`, one at `<HOME>/.agents/skills`, and one at
`<CODEX_HOME>/skills`. It reports only fixture booleans and counts. Before and
after the probe, it hashes the file listings and contents under the personal
Codex session and skill roots without printing their names or contents. A
changing session hash is inconclusive when the IDE is concurrently writing its
own session; it does not prove that this probe wrote there.

The app-server may briefly hold a Windows handle after termination. Temporary
cleanup ignores that race; the probe never deletes or moves personal files.
Use an OS temp cleanup policy for any residual `laomedo-119-*` scratch folder.

## Observed output

One completed run on 2026-09-28 reported the repo fixture and `CODEX_HOME`
fixture as discovered, the `$HOME/.agents/skills` fixture as undiscovered,
zero discovered paths outside scratch under the personal home, and zero model
calls. The personal skill directory hashes were unchanged. The personal
session directory hash varied across repeated runs while this IDE Codex
session was active, so session-file isolation remains unproven by this probe.

The current [Codex skill documentation](https://learn.chatgpt.com/docs/build-skills)
describes `$HOME/.agents/skills` as a user location. The observed CLI predates
the SDK version inventoried in #118; do not generalize this result to newer
versions. `skills/list` is documented in the
[Codex app-server reference](https://learn.chatgpt.com/docs/app-server).

No Claude executable or dedicated Laomedo project credential was available
for this run. Claude discovery and selected-skill execution were not tested.

## Read-only manifest pilot

`snapshot_bundle.py` applies an explicit overlay manifest to two existing
skills with different layouts: `ui-design` has a small script bundle and
`html-to-drawio` has scripts plus references. The manifests are local to this
experiment. The source skills are read and hashed, never edited. Reproduce
from the Laomedo repository root when the sibling `my-skills` checkout exists:

```powershell
python experiments/feasibility/119/snapshot_bundle.py --source '..\my-skills\ui-design' --manifest experiments/feasibility/119/ui-design.manifest.json --select start-with-evidence --output experiments/feasibility/119/ui-design.snapshot.json
python experiments/feasibility/119/snapshot_bundle.py --source '..\my-skills\graphics\html-to-drawio' --manifest experiments/feasibility/119/html-to-drawio.manifest.json --select usage-example --output experiments/feasibility/119/html-to-drawio.snapshot.json
```

The pilot assigns explicit stable item IDs to exact headings and lists each
item's file dependencies. It rejects duplicate IDs, missing or escaped files,
and ambiguous headings. Per-file SHA-256 hashes are combined into a canonical
tree hash by sorting relative paths and hashing each path, NUL, file hash, and
newline. The snapshots include selected item IDs and dependency files.

Both selected headings live in a `SKILL.md` that contains other sections.
Native discovery would expose the whole file, so the selection records say
`direct_context_required`. A future subset materializer would need to render
the selected text and dependencies into a new frozen bundle, or pass the
selection as direct context while labeling it as such. The committed JSON
contains hashes and relative paths only, no copied skill content.
