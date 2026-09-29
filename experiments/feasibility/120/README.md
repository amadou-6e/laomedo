# Issue 120: Codex runner isolation, persistence, and settings

No-model probes for [specs issue #120](https://github.com/amadou-6e/specs/issues/120).
These probes investigate whether Codex can run as a persistent Laomedo flow
step with model/effort control, private sessions and skills, and inspectable
native events. They reuse #119's skill-discovery results; retest only where
the runner version differs.

## Requirements

- Python 3.9 or newer (stdlib only; no pip dependencies).
- Codex CLI binary. The observed version is pinned in the findings doc.
- `_shared.py` is the common utility module.

## Probes

All probes emit sanitized JSON to stdout and write stderr logs to `_scratch_120_*`
directories. Personal profile hashes are compared before and after each run.

### `probe_model_effort.py` -- No credential needed

Lists available models with their supported reasoning efforts, tests that a
supported effort is accepted and an unsupported effort is explicitly rejected,
and tests rejection of an unknown model ID.

```powershell
python experiments/feasibility/120/probe_model_effort.py --codex '<absolute-path-to-codex.exe>'
```

### `probe_isolation.py` -- No credential needed

Verifies fixture skills are discovered in the private project, no skills from
the user's personal profile are loaded, and starting a thread + turn (without
a model call) does not modify personal session or skill directories.

```powershell
python experiments/feasibility/120/probe_isolation.py --codex '<absolute-path-to-codex.exe>'
```

### `probe_persistence.py` -- No credential needed

Creates a thread with one turn, stops the app-server, restarts it, and
attempts resume against the same thread ID. Tests thread/list support and
the rejection behavior when the workspace snapshot is removed.

```powershell
python experiments/feasibility/120/probe_persistence.py --codex '<absolute-path-to-codex.exe>'
```

### `probe_stream_events.py` -- Credential required

Submits a turn with a synthetic skill that triggers a tool call (directory
listing). Captures every event emitted: items, tool calls, tool results,
and token usage. Redacted event kinds and counts go to stdout; raw session
and stderr remain in the private state directory. Requires file-backed
ChatGPT auth at `<state-dir>/codex-home/auth.json`.

```powershell
# Preflight (no model turn)
python experiments/feasibility/120/probe_stream_events.py --codex '<path>' --state-dir '<private-state-dir>'

# Submit the model turn (after preflight confirms fixture, auth, connectivity)
python experiments/feasibility/120/probe_stream_events.py --codex '<path>' --state-dir '<private-state-dir>' --run
```

## Credential gate

No dedicated Laomedo project/service credential was available at writing.
The stream probe includes a credential gate that checks auth mode and
connectivity before any model call. The preflight (`--run` omitted) can
confirm fixture discovery, model listing, and connectivity without spending.
If a suitable credential becomes available, run the preflight first, then
`--run` with the same `--state-dir`.

## Read-only manifest

No file manifests are produced in this spike unless the stream events probe
is run, in which case redacted event arrays appear in the summary JSON.

## Isolation guarantees

- Private `HOME`, `USERPROFILE`, and `CODEX_HOME` are constructed.
- Personal skill and session roots are hashed before and after; results are
  printed as sanitized comparison booleans.
- No personal file contents, names, or paths are emitted.
- Scratch directories start with `_scratch_120_` and are excluded by
  `.gitignore`.
