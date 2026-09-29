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
thread still reported `readOnly`. Its private turn context did record
`workspace-write`, yet the agent said its read and patch actions were blocked
by environment policy. A credential-free comparison with Codex CLI 0.159.0
showed the same thread response and successful command canary; upgrading the
binary alone did not resolve the discrepancy. Its `configRequirements/read`
response contained no active requirements, and `config/read` reported no
configured sandbox or approval default in the disposable environment. These
read-only responses do not establish why `thread/start` resolves to `readOnly`.
The personal skill and auth hashes stayed
unchanged; the personal session-root hash changed during concurrent IDE use
and cannot be attributed. No agent-edit resume was attempted because there was
no valid first edit. The sanitized facts and API-equivalent estimate are in
`observations.json`; raw traces and the credential remain outside Git.

The current runner is a **no-go for automated skill editing**. Post-edit
validation works on synthetic changes, but the model-backed edit and the
integrated runner write boundary are not established. The remaining four #122 turns
should be reserved for a revised runner with a verified effective write grant
and observable tool calls. The ChatGPT run has no direct API bill; the estimate
is API-equivalent only, using the pinned #120 Luna rate assumptions.

### Credential-free native Windows boundary check

On the locally installed Codex CLI 0.159.0, a synthetic `command/exec` probe
used a draft and a sibling store under a disposable root. With no explicit
Windows sandbox mode, both a requested `readOnly` command and a
`workspaceWrite` command wrote outside their intended boundaries. The
`sandboxPolicy` field alone was therefore not evidence of enforcement.

An explicit per-process `windows.sandbox="elevated"` override, run outside the
calling tool's own restricted context, gave the expected filesystem result:
the read-only write failed, the draft write succeeded, and the sibling-store
write failed. The protected store file stayed unchanged. An explicit
`unelevated` attempt denied all three writes, including the allowed draft
write, so it was not usable in this environment. These were direct synthetic
commands with no model call or credential. Network access was enabled for the
synthetic `echo` command to avoid an unrelated offline startup failure; network
isolation was not tested. The earlier model turns still had no agent tool call,
so this result does not establish automated skill editing.

The probe used a CLI override rather than changing `config.toml` and did not
request Windows sandbox setup. Elevated mode generated protected setup state
that ordinary cleanup could not delete. That exact disposable directory was
moved out of the Git worktree into the ignored `probe-artifacts.local/` folder
at the AGENTVIZ workspace root. Do not open or publish its `.sandbox-secrets`
content. An administrator cleanup path remains to be tested.

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

`probe_appserver_permissions.py` compares CLI permission surfaces without
loading credentials or submitting a turn. `inspect_private_turn_policy.py`
reads only the sandbox and approval fields for a named private turn; its
output omits prompts, file contents, and credentials.

`probe_native_write_boundary.py` checks a read-only write, an allowed draft
write, and a forbidden sibling-store write without credentials or model turns.
It uses a private scratch root outside Git and prints command status with short
error excerpts from these synthetic commands. Elevated mode may retain a
protected scratch directory if Windows denies cleanup. Run it with
`--windows-mode elevated` and an explicit Codex
binary path after reviewing that boundary and the local sandbox setup.
