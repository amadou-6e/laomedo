# Issue 122: versioned Skill Draft feasibility

This is a disposable proof for [specs issue #122](https://github.com/amadou-6e/specs/issues/122).
It is stacked on the #120 Codex runner branch and imports that branch's
`_shared.py` app-server client. Python 3.9+ standard library is the only Python
dependency. The observed Codex executable was `codex-cli
0.155.0-alpha.16.3` in the first two turns, pinned by hash in the #120 report;
later tests used Codex CLI 0.159.0.

Current result on 2026-09-30: an isolated Codex agent edited the synthetic
draft, and a restarted app-server resumed the same native thread against the
frozen post-edit draft. The final draft contains only the intended `SKILL.md`,
passes structural validation and the fixed case, and is promotion eligible.
The canonical skill was never modified or promoted. The original six authorized
model turns were used. The user then authorized one supplemental retry, raising
the retained ledger cap to seven without resetting its count. Turn 7 completed
with an agent-originated forbidden-write denial. The credential-free network
probe reached its loopback fixture with network access both enabled and
disabled; external egress and sandbox identity checks remain incomplete.

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
without copying its credential. It uses a separate persistent turn ledger
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

The first two runs were a **no-go for automated skill editing**. Post-edit
validation worked on synthetic changes, but neither model-backed turn edited
the draft or emitted a tool item. A later follow-up found a working agent tool
path, described below. The ChatGPT runs have no direct API bill; the recorded
estimate for the first two turns is API-equivalent only, using the pinned #120
Luna rate assumptions.

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
moved out of the Laomedo worktree into the ignored `probe-artifacts.local/` folder
at the AGENTVIZ workspace root. Do not open or publish its `.sandbox-secrets`
content. An administrator cleanup path remains to be tested.

An explicit unelevated retest with CLI 0.159.0 first failed inside the calling
tool sandbox with `CreateRestrictedToken failed: 87`, before any synthetic
command ran. Outside that outer sandbox, Codex reported `unelevated` in
`config/read`. The read-only and sibling-store writes were denied, but the
allowed draft write was also denied with `Access is denied.` This reproduces
the earlier unusable filesystem result without a model turn or credential. A
second run with the same executable and a disposable AppData draft produced
the same three denials, so the result is not specific to the AGENTVIZ scratch
location. The successful loopback `curl` command below shows command execution
itself works; the observed blocker is creating the allowed file. An upstream
[Windows report](https://github.com/openai/codex/issues/34179) describes a
similar unelevated write failure, but does not establish the cause here.

The direct CLI boundary probe `probe_ide_profile_boundary.py` used the IDE's
`codex-cli 0.155.0-alpha.16.3` binary (SHA-256
`589f2546cc1e86703da326b00741f8b7a58fd182a1a90499faa0beebf22a24e2`),
the existing persistent private `CODEX_HOME`, and an invocation-only named
permission profile. Its workspace root was a disposable draft, with a sibling
store outside that root. After a probe correction to use PowerShell's
per-process `RemoteSigned` setting and a host-created draft file, the command
edited and read back the allowed file, while the sibling write returned
`UnauthorizedAccessException`. Host verification confirmed the edited content
and unchanged sibling sentinel. No model turn, credential copy, or persistent
Codex configuration change was involved. This is a direct-command boundary
result, not an agent edit or proof of restricted reads.

Pinning the IDE binary did not eliminate repeated elevated sandbox setup. The
private sandbox log reported `sandbox users missing or incompatible with marker
version` and ran full user provisioning on successive probe invocations. A
write-root refresh also ran for each disposable draft. The private marker was
present, version 5, and its ACL granted the Windows user Full Control, so a
missing or unreadable marker is not established as the cause. No further
sandbox runs were made to diagnose the mismatch. The result is consistent with
the [cross-runtime state issue](https://github.com/openai/codex/issues/36865),
but that report does not identify the exact cause on this machine.

### Follow-up on 2026-09-30: agent edit and failed draft inventory

One additional authorized turn used Codex CLI 0.159.0, a per-process
`windows.sandbox="elevated"` override, and the existing private ChatGPT profile.
It ran outside the calling tool's restricted context. This combination returned
`workspaceWrite` at `thread/start`, and the turn trace contained completed
command and file-change items. The agent read `SKILL.md`, appended the requested
example, and read it again. The canonical skill stayed unchanged. This was an
agent edit, not just a direct `command/exec` canary. Three of the six #122
model turns are now used; three remain. Resume was intentionally skipped.

The draft was not promotion eligible. `validate_draft` reported `skill_missing`
and `unapproved_directory` because its inventory rejects the whole draft tree
when it finds an unapproved path. The file itself was still present and contained
the requested change. PowerShell had also written a literal
`%SystemDrive%/ProgramData/Microsoft/Windows/Caches/` tree into the draft. A
clean copy containing only the edited `SKILL.md` passed structural validation,
produced a patch, and passed the fixed case. The original run directory was not
altered for that check.

A separate credential-free PowerShell read reproduced the cache tree when the
runner's constructed environment omitted `SystemDrive`; supplying the drive
from `SystemRoot` prevented it. This identifies the missing environment variable
as the cause of this incidental draft write. At this stage, no shared runner
environment change had been applied. The earlier shell and patch denials remain
traceable to the original permission path; the successful follow-up changed
the CLI version, Windows sandbox mode, and calling-tool context together, so
it does not isolate which one resolved each denial.
The diagnostic left another protected scratch directory under the ignored
AGENTVIZ `probe-artifacts.local/` root, ignored by Git; ordinary cleanup may be denied.

### Follow-up on 2026-09-30: valid edit and native resume

The runner now supplies `SystemDrive` derived from `SystemRoot` in its clean
private environment. A credential-free elevated PowerShell check again created
the literal cache directory when that variable was deliberately removed and
left the draft clean when it was present. A regression test checks the
constructed environment. The edit probe also verifies resolved draft and
snapshot paths stay under its exact run root before recursive restore.

One new two-turn run used Codex CLI 0.159.0 with the per-process elevated
Windows sandbox and the existing private profile. Turn 4 made the requested
edit through observed command and file-change items. The post-run draft had
only `SKILL.md`, no validation violations, a patch, and a passing fixed case.
The runner froze that draft, injected a disposable drift file, proved a missing
snapshot was refused without changing the draft, and restored the frozen hash.
After app-server restart, turn 5 resumed the same native thread, saw the first
example, and added the second. The final draft again contained only `SKILL.md`,
with no validation violations and a passing fixed case. The final result is
promotion eligible, but the probe performed no promotion. The canonical base
tree stayed unchanged. Sanitized IDs, aggregate usage, and hashes are recorded
in `observations.json`; private raw traces remain outside Git.

## Reproduction

From the Laomedo repository root:

```powershell
python -m unittest discover -s experiments/feasibility/122 -p 'test_*.py' -v
python experiments/feasibility/122/probe_draft_guards.py
```

The model-backed probe requires an existing, access-restricted private #120
profile and a distinct #122 state root beneath it, both outside Git. Do not
copy the personal auth file or create another login. Use the same state root
for every attempt so the turn ledger cannot reset:

```powershell
$privateProfile = Join-Path $env:LOCALAPPDATA 'Laomedo\feasibility-120'
$issueState = Join-Path $privateProfile 'issue-122'
$codexBinary = (Get-Command codex).Source
python experiments/feasibility/122/probe_codex_edit.py --codex $codexBinary --profile-dir $privateProfile --state-dir $issueState
# Historical bounded invocation; do not rerun against the current five-turn ledger:
python experiments/feasibility/122/probe_codex_edit.py --codex $codexBinary --profile-dir $privateProfile --state-dir $issueState --windows-mode elevated --first-only --run
# The valid edit and resume used the same command without --first-only.
```

Seven submitted turns count in the private ledger. The user-approved
supplemental turn is used, so the cap is exhausted. The probe
never prints credential content or raw model text. The profile must remain
persistent across runs because its own refresh may invalidate the interactive
login, as documented in #120. Production authentication belongs to #129.

`probe_appserver_permissions.py` compares CLI permission surfaces without
loading credentials or submitting a turn. `inspect_private_turn_policy.py`
reads only the sandbox and approval fields for a named private turn; its
output omits prompts, file contents, and credentials.

`probe_native_write_boundary.py` checks a read-only write, an allowed draft
write, and a forbidden sibling-store write without credentials or model turns.
It uses an ignored scratch root in the AGENTVIZ checkout and prints command status with short
error excerpts from these synthetic commands. Elevated mode may retain a
protected scratch directory if Windows denies cleanup. Run it with
`--windows-mode elevated` and an explicit Codex
binary path after reviewing that boundary and the local sandbox setup.
`probe_ide_profile_boundary.py` tests the IDE binary with a named profile and
the existing private Codex home. It may trigger Windows sandbox provisioning;
do not treat its `approval_policy` or profile settings as a way to suppress UAC.

`probe_windows_env.py` reproduces the PowerShell cache side effect with and
without `SystemDrive`, using no credential or model turn. It uses disposable
scratch in the ignored AGENTVIZ directory and may retain protected sandbox setup state. Run it with
the same explicit Codex binary path. `verify_clean_skill.py` takes one private
run directory and validates a temporary copy containing only that run's edited
`SKILL.md`; it does not alter the original run.

### Final bounded negative probes

`probe_network_boundary.py` serves a synthetic loopback marker and asks the
elevated app-server to fetch it with network access enabled and disabled. Both
attempts stopped at the first network-enabled `command/exec` timeout. Neither
allow nor deny behavior was observed, so this does not establish network
isolation. The probe uses no credential or model turn.

`probe_agent_forbidden_write.py` reuses the existing private profile and
turn ledger. Its first run timed out on a credential-free direct-command
canary without reserving a model turn. A second run skipped that current
canary using the earlier successful elevated direct-command boundary result.
It started a native workspace-write thread and submitted turn 6, asking for
one write to a synthetic sibling-store file. The agent said it would attempt
the write, but the 120-second turn wait timed out with no command or file-change
item in the stream. The target remained absent and the synthetic sentinel was
unchanged. This is an inconclusive agent-originated boundary test, not a
demonstrated denial. That attempt exhausted the original six-turn cap.

The later user-approved cap extension permitted one additional turn, recorded
as attempt 7 in the same ledger. The retry probe required both a successful
draft write and a denied outside-store write from `command/exec` before it
reserved that turn. Its first preflight caught a flawed fixture: the synthetic
"forbidden" store was under the runner state used for `TEMP` and `TMP`, so the
direct write succeeded. No turn was reserved. Moving the store to a separate
private directory outside all runner writable roots produced the expected
direct denial. Turn 7 then completed. Its command item shows PowerShell
attempted to write the exact outside-store file and received access denied
with exit code 1. The target remained absent, and the sentinel hash stayed
unchanged. The separate synthetic store was cleaned up after recording the
result.

The Codex elevated sandbox log from turn 6 says sandbox
setup was required because its users were missing or incompatible, then has
no setup-completion line. This identifies a sandbox setup stall as the likely
cause of the command timeouts, but it does not establish which Windows setup
step failed. The sandbox accounts are present. The successful seventh run did
not require an additional configuration change.

The network probe was repeated without a model turn, reusing the existing
private sandbox profile. One completed run reached the synthetic HTTP
loopback fixture with both `networkAccess: true` and `false`, despite the
documented boolean field for `workspaceWrite`. This fails the probe's
loopback-isolation condition. Follow-up sandbox-user identity and external
egress checks stalled during elevated sandbox setup, so the result does not
establish whether external Internet egress is blocked. A fresh private
profile also stalled before its first command. Do not treat `networkAccess:
false` as a verified boundary on this host.

A separate, credential-free unelevated run with CLI 0.159.0 also reached the
loopback fixture with `networkAccess: false`. Its enabled positive control
reached the same fixture. This tests loopback only; it does not establish
external egress behavior. The probe now requires `--windows-mode` explicitly,
so a later run cannot enter elevated setup by omission.
The user elected to defer network-isolation work for the local prototype. This
does not fix the unelevated allowed-draft-write failure or establish a
production confinement boundary.

The failed first preflight also showed that `TEMP` and `TMP` must not point to
the whole issue state. That root contained the synthetic canonical store in
the earlier edit probe, so unchanged canonical content was an observation,
not proof of an OS write boundary around it. The #122 edit and negative probes
now set both variables to a dedicated `state/tmp` sibling. A direct check of
canonical write protection with this narrower environment timed out during
native sandbox setup. Existing state may retain earlier write ACL grants, so
canonical protection remains unverified; a production runner needs a store
outside every agent writable root and an explicit write-denial canary.

Three earlier elevated-sandbox scratch directories remain under the ignored
`probe-artifacts.local/` root inside the AGENTVIZ checkout but ignored by Git.
Exact-path recursive cleanup was
attempted, but Windows denied access to their `sandbox_users.json` setup files
even from the elevated tool context. They require an administrator cleanup
route; no protected file contents were opened or published.

### Container route: credential-free filesystem proof

On 2026-09-30, Docker Desktop's Linux engine built
`container/Dockerfile` with Codex CLI 0.159.2 and Bubblewrap. The base image
resolved to `node:22-bookworm-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c`.
No Codex login, credential, model call, or native Windows elevated sandbox was
used. Neither probe changes the Docker daemon or the user's Codex settings.

`probe_container_mount_boundary.py` ran as non-root UID 65532 with no network,
all capabilities dropped, no-new-privileges, a read-only container root, and
only a disposable draft mounted writable. It edited the draft and was denied a
write to a canonical read-only mount. Host-side checks found the expected draft
edit and unchanged canonical sentinel.

`probe_container_codex_boundary.py` then exercised Codex's Linux command
sandbox as UID 10001, with no network, all capabilities dropped, and
no-new-privileges. A separate synthetic store was deliberately mounted
**writable** for this test: a command outside Codex wrote its control file,
while `codex sandbox -P container-test -C /draft` edited the draft but received
`Read-only file system` when it tried to overwrite the store sentinel. The
canonical read-only mount also denied a write. Host-side checks found the
draft edit, the positive-control file, and unchanged store and canonical
sentinels. The probe's own configuration grants write access only to the
workspace root and is copied into a disposable, container-only `CODEX_HOME`.
It explicitly denies reads of a synthetic credential file in that home. A
command outside Codex read the fake marker, while the same read through Codex's
sandbox returned `Permission denied`. This exercises the documented
[permission-profile deny rule](https://learn.chatgpt.com/docs/permissions)
without touching any real login.
An initial attempt with `CODEX_HOME` under `/tmp` failed before commands ran
because Codex refused to create its Linux helper there; placing it under
`/home/runner/.codex` resolved that startup failure.

Reproduce without credentials or model calls from the Laomedo root:

```powershell
docker build --tag laomedo-codex-boundary:0.159.2 experiments/feasibility/122/container
python experiments/feasibility/122/probe_container_mount_boundary.py
python experiments/feasibility/122/probe_container_codex_boundary.py
```

The tested filesystem result supports a container-based runner prototype on
this machine without Windows sandbox provisioning prompts. It does not yet
establish an agent-originated denial, a persistent app-server session, or a
safe authentication flow. The fake-credential result is a direct-command check
of one exact deny path, not a complete secrets audit. The #122 model-turn
ledger remains 7/7; these were
credential-free direct-command probes. The synthetic writable store belongs
only to the diagnostic. A real runner should expose the canonical store to
the container read-only or not mount it at all, and use a distinct private
credential volume that agent commands cannot read. Network isolation remains
deferred for the local prototype.

### Container route: isolated login and two model turns

The user then authorized a Docker-route retry. The original #122 private
ledger was preserved at 7/7. A separate private `issue-122-docker` ledger was
started outside Git and now records **2/2** submitted turns. The counters were
read independently after both runs. No Windows Codex sandbox was launched.

Docker received one copy of the existing isolated #120 ChatGPT login in the
named `laomedo-122-docker-auth` volume. The personal Codex profile was not
mounted. The first volume initialization attempt failed before copying because
the volume was root-owned; a one-time provisioning container then copied and
verified the file without printing it. The runner used that persistent volume
on both turns. This is a temporary feasibility handoff, not the production
authentication design. A refresh in the Docker copy could invalidate another
copy of the same login; do not use both runners concurrently. The volume also
contains private raw session data and must never be exported or committed.
The Docker login file still matched the isolated #120 source byte-for-byte
after both turns; this does not remove the future refresh-token rotation risk.

`container/runner-config.toml` selects a named permission profile that writes
the draft, denies reads of `/home/runner/.codex/auth.json`, and requests no
command network access. Docker itself used bridge networking so the controller
could reach the model; the agent's network boundary was **not tested**. The
app-server's direct-command preflight wrote a draft canary, denied a write to
the synthetic store, and denied a read of the login file. The store was
deliberately mounted writable as a diagnostic, so the denial came from Codex's
inner Linux sandbox. Neither denied command printed credential content.

Turn 1 used `gpt-6-luna` at low effort and completed. The agent's command
events show it edited and read `SKILL.md`; the draft gained the requested
example and contained no extra file. Final validation found only `SKILL.md`
changed, no structural violations, and a passing fixed case. The canonical
skill and synthetic store were unchanged. The agent did not make the requested
forbidden-write call, so
the agent-originated store boundary was not established. Turn 2 restarted the
container/app-server, resumed the **same native thread** using the persistent
volume, and completed. Its trace contains no command event; the agent message
indicates a refusal, and the draft and store remained unchanged. This confirms
persistent thread resume but still does not prove an agent-originated denied
write. The absence of a write is not a sandbox denial.

The new scripts are `probe_container_agent_edit.py`,
`probe_container_agent_resume.py`, and `inspect_container_agent_trace.py`.
They write raw traces only into the private state directory and print
sanitized summaries. Their ledger is exhausted; rerunning them cannot submit
another model turn. The result is a **go for a local container-based edit and
resume prototype**, with direct-command write and credential-read boundaries
observed. Agent-originated denial, full credential isolation, and network
isolation remain open before an untrusted or multi-user runner.
