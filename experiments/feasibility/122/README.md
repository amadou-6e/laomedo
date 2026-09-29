# Issue 122: versioned Skill Draft feasibility

This is a disposable proof for [specs issue #122](https://github.com/amadou-6e/specs/issues/122).
It is stacked on the #120 Codex runner branch and imports that branch's
`_shared.py` app-server client. Python 3.9+ standard library is the only Python
dependency. The observed Codex executable was `codex-cli
0.155.0-alpha.16.3`, pinned by hash in the #120 report.

## Proof boundaries

`edit-policy.json` is an independently versioned policy, hashed into an
`EditPolicyRef`. It allows `SKILL.md` and one Markdown example, bans scripts,
dependencies and assets, and names two deterministic validators. The probe
copies a synthetic canonical skill into a draft, records both tree hashes,
diff, policy ref, changed paths, and fixed-case results. It never promotes a
draft. Agent IDs and trace refs are null for synthetic cases rather than
fabricated.

`probe_draft_guards.py` runs allowed and forbidden changes, partial failure,
timeout, a concurrent base revision, and missing/post-run snapshot cases. It
rejects symlinks and Windows junctions before reading their targets. On this
host, native symlink creation was denied; a Windows junction test passed.
This validator detects disallowed changes **after** an edit. It is not an OS
write boundary and cannot prove a forbidden write was prevented.

`probe_codex_edit.py` reuses the private ChatGPT profile provisioned for #120
without copying its credential. It uses a separate persistent six-turn ledger
under the #122 state root, new run directories for every attempt, and raw
app-server logs only in private state. It performs a credential-free
`command/exec` write canary before a paid edit. It requests a turn-level
`workspaceWrite` policy; the pinned CLI's `thread/start` schema spells its
separate sandbox mode `workspace-write`. The reported thread policy and actual
file changes are recorded separately.

## Observed on 2026-09-29

Two of six allowed Codex turns were submitted on `gpt-6-luna` at low effort.
Both completed, but neither changed `SKILL.md`, and neither stream contained a
tool item. The first requested thread sandbox `workspace-write`, yet the
server returned `readOnly`. The second added an explicit turn-level
`workspaceWrite` policy and passed the credential-free write canary, but the
thread still reported `readOnly` and the agent said its read and patch actions
were blocked by environment policy. The personal skill and auth hashes stayed
unchanged; the personal session-root hash changed during concurrent IDE use
and cannot be attributed. No agent-edit resume was attempted because there was
no valid first edit. The sanitized facts and API-equivalent estimate are in
`observations.json`; raw traces and the credential remain outside Git.

The current runner is a **no-go for automated skill editing**. Post-edit
validation works on synthetic changes, but the model-backed edit and the
runtime write boundary are not established. The remaining four #122 turns
should be reserved for a revised runner with a verified effective write grant
and observable tool calls. The ChatGPT run has no direct API bill; the estimate
is API-equivalent only, using the pinned #120 Luna rate assumptions.

## Reproduction

From the Laomedo repository root:

```powershell
python -m unittest discover -s experiments/feasibility/122 -p 'test_*.py' -v
python experiments/feasibility/122/probe_draft_guards.py
```

The model-backed probe requires an existing, access-restricted private #120
profile and a distinct #122 state root beneath it, both outside Git. Do not
copy the personal auth file or create another login. Use the same state root
for every attempt so the six-turn ledger cannot reset:

```powershell
$privateProfile = Join-Path $env:LOCALAPPDATA 'Laomedo\feasibility-120'
$issueState = Join-Path $privateProfile 'issue-122'
$codexBinary = (Get-Command codex).Source
python experiments/feasibility/122/probe_codex_edit.py --codex $codexBinary --profile-dir $privateProfile --state-dir $issueState
# Only after the effective write grant is fixed and reviewed:
python experiments/feasibility/122/probe_codex_edit.py --codex $codexBinary --profile-dir $privateProfile --state-dir $issueState --run
```

The two submitted turns already counted in the private ledger. The probe
never prints credential content or raw model text. The profile must remain
persistent across runs because its own refresh may invalidate the interactive
login, as documented in #120. Production authentication belongs to #129.
