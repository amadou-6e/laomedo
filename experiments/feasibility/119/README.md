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
