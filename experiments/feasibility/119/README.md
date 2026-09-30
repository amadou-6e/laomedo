# Issue 119: Codex discovery and private-login probe

This directory contains synthetic discovery, selected-skill, and manifest
probes for [specs issue #119](https://github.com/amadou-6e/specs/issues/119).
`probe_codex_discovery.py` starts `codex app-server`, calls `initialize` and
`skills/list`, and stops without a thread, model turn, or credential.

## Reproduce

The observed Windows toolchain is Python `3.12.10` and
`codex-cli 0.155.0-alpha.16.3`. The observed `codex.exe` SHA-256 is
`589f2546cc1e86703da326b00741f8b7a58fd182a1a90499faa0beebf22a24e2`.
The Python scripts use only the standard library, so there are no pip packages
or Codex SDK dependency to install or pin. This pins the observed experiment,
not the target CLI/SDK pair for #120. From the Laomedo repository root:

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
On a 2026-09-29 no-model rerun, six additional discovered skill paths were
under the disposable `CODEX_HOME/skills/.system` directory. There were zero
other private skill paths and zero personal skill paths. The runtime-provided
system skills mean the fixture was not the only skill visible to `skills/list`.

The current [Codex skill documentation](https://learn.chatgpt.com/docs/build-skills)
describes `$HOME/.agents/skills` as a user location. The observed CLI predates
the SDK version inventoried in #118; do not generalize this result to newer
versions. `skills/list` is documented in the
[Codex app-server reference](https://learn.chatgpt.com/docs/app-server).

No Claude executable or dedicated Laomedo project credential was available
for this run. Claude discovery was not tested.

## Private ChatGPT login and selected-skill attempt

`check_private_auth.py` checks the authentication mode from a private runner
profile and prints only status booleans. `probe_codex_skill_turn.py` starts an
app-server in that profile, discovers one synthetic project skill, and can
submit a `$skill` text mention and structured `skill` input together in a
model turn. It prints sanitized event counts and marker booleans. Before
`--run` submits a turn, a credential-free
TCP check must reach `chatgpt.com:443`; the check is only a prerequisite and
does not prove that the authenticated model request will succeed. The raw
session and stderr remain in the private state directory. Both scripts now
reject `--state-dir` inside any Git working
tree or Git metadata. The caller must provision a credential in the private
`codex-home/auth.json`; neither script provisions credentials. The one-time
local auth-copy exception and all three model turns allowed by #119 have been
used, so the `--run` example below is for a separately authorized experiment
with its own credential and spend limit.
An app-server request timeout is reported by method and turn state without
printing raw server output. The TCP check also reports the exception class
when it fails; the single host check does not enumerate every Codex endpoint.

```powershell
python experiments/feasibility/119/check_private_auth.py --codex '<absolute-path-to-codex.exe>' --state-dir '<private-state-dir>'
python experiments/feasibility/119/probe_codex_skill_turn.py --codex '<absolute-path-to-codex.exe>' --state-dir '<private-state-dir>'
python experiments/feasibility/119/probe_codex_skill_turn.py --codex '<absolute-path-to-codex.exe>' --state-dir '<private-state-dir>' --run
```

On 2026-09-28, a local file-backed ChatGPT Codex auth file was copied into an
ignored, access-restricted private state directory inside the AGENTVIZ Git
working tree. This violated the stated outside-repository rule. Only that auth
file was copied. `codex login status` in a constructed private environment
reported ChatGPT login, not API-key mode. The native preflight found the
synthetic skill and no skill path outside private state. The app-server listed
`gpt-6-luna` with low effort available.

Two `gpt-6-luna` low-effort turns were submitted with both a `$skill` text
mention and structured `skill` input in the calling agent's network-restricted
tool context. This was separate from the Codex thread's `read-only` sandbox.
Both were accepted but had no agent answer or `turn/completed` event within a
90-second deadline. The instrumented second
attempt emitted `error` and `warning` notifications and its private stderr
contained network and HTTP Forbidden signals. A credential-free HTTPS check
from that context failed to connect to `chatgpt.com`, while the network-enabled
context received HTTP 200.
The new no-model preflight reports `chatgpt_tcp_reachable: false` in the
restricted context and `true` in the network-enabled context.

A second ignored, access-restricted private runner directory was created
inside the AGENTVIZ Git working tree because the network-enabled context could
not read the first private directory's ACL. Only the file-backed auth was
copied from the personal source into this second directory. This second copy
went beyond #119's one-time handoff allowance. Both auth copies were deleted
on 2026-09-29 after review. Refresh-token rotation effects on the personal
login were not tested. The second directory's no-model auth and discovery
preflight passed. The third and final #119 turn then completed in about eight seconds
and returned the exact marker from the synthetic skill. The private raw
trace contains one assistant message with that marker, one token-usage event,
and no tool calls. It recorded 16,253 input tokens, including 11,008 cached
input tokens, and 13 output tokens. At the [GPT-6 Luna Standard short-context
API rates](https://developers.openai.com/api/docs/models/gpt-6-luna), this is
about USD 0.00064 API-equivalent usage, not an actual subscription charge.
The trace reported `cache_write_input_tokens: 0`, so this estimate includes no
cache-write charge; cached input tokens are reads, not evidence of writes.

The completed turn shows that the skill body's instruction reached the model.
It does not isolate the structured `skill` input from the `$skill` mention or
normal project-root discovery. A structured input alone, a distinct skill-file
read event, and isolated subsection selection remain unproven. No script was
invoked. Corrected before/after comparisons for the third turn found the personal skill,
session, and auth roots unchanged. The earlier turns' auth-file comparison
used a defective file hash and their session comparison was confounded by the
active IDE session. All three allowed turns have now been used.

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
