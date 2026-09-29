# Issue 121: Claude runner isolation, persistence, and settings

Probes for [specs issue #121](https://github.com/amadou-6e/specs/issues/121).
They verify #119's documented Claude skill paths against the pinned SDK and
investigate whether Claude Code can run as an isolated, resumable Laomedo flow
step through the Claude Agent SDK.

## Requirements

- Python 3.10+ with `claude-agent-sdk==0.2.161` (`requirements.txt`).
- Node.js 18+ for the CLI subprocess.
- A Claude Code CLI the SDK can run. The SDK looks for a bundled CLI, then a
  native `claude.exe` on Windows. An npm `claude.cmd` shim is refused.
- `_shared.py` is the harness: version capture, CLI resolution, credential
  gate, message redaction, and print-once failure handling.

## Probes

| Probe | Credential | Model call | What it tests |
| --- | --- | --- | --- |
| `probe_environment.py` | none (forced-invalid key) | no | SDK/CLI versions, CLI resolution, explicit failure without a credential, config-dir plumbing |
| `probe_isolation_settings.py` | API key | yes | `setting_sources` control over planted decoy skills, init `skills` array, requested vs effective model/effort, invalid settings rejection |
| `probe_stream_resume.py` | API key | yes | streamed `ToolUseBlock`/`ToolResultBlock` linkage, explicit failures, `interrupt()` cancellation, resume in a fresh CLI process, unknown-session rejection |

The environment probe passes `ANTHROPIC_API_KEY=invalid-laomedo-121-no-spend`
so session start fails at authentication and cannot bill. The two credentialed
probes count a turn on submission, bound every call with `max_turns` and
`max_budget_usd`, and report `observed_cost_usd` from `ResultMessage`
totals, which are real provider spend under an API-key credential.

## Credential gate

Both credentialed probes stop before any model call unless the gate passes.
The gate accepts only a dedicated `ANTHROPIC_API_KEY` from the runner
environment, rejects a state dir inside a git working tree, rejects a personal
OAuth token file present in the private config dir (a copied login), and
requires TCP reachability to `api.anthropic.com`. Per the SDK docs,
`ANTHROPIC_API_KEY` takes precedence over a subscription login when present.

## Observed on the authoring machine (2026-09-29)

`probe_environment.py` ran with `claude-agent-sdk 0.2.161` (Python 3.12.10,
Node v20.11.1, Windows AMD64). No CLI resolved: the PyPI wheel ships no
bundled CLI on this platform and no native `claude.exe` is installed, so
session start fails with `CLINotFoundError` before any authentication or model
call. Personal roots were unchanged. The two credentialed probes have not been
executed; they require a native `claude.exe` install and a dedicated key.

## Scope limit: conversation versus workspace

The SDK persists conversation history only. Session files live under
`$CLAUDE_CONFIG_DIR/projects/<encoded-cwd>/<session-id>.jsonl`. Restoring the
last post-run workspace snapshot before a resume is the Laomedo runner
registry's responsibility; `probe_stream_resume.py` fingerprints the workspace
before and after and records the distinction instead of claiming the SDK
provides it.

## Reproduction

From the Laomedo repository root:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r experiments/feasibility/121/requirements.txt
.venv\Scripts\python experiments/feasibility/121/probe_environment.py
.venv\Scripts\python experiments/feasibility/121/probe_isolation_settings.py --state-dir '<private-state-dir>'
.venv\Scripts\python experiments/feasibility/121/probe_stream_resume.py --state-dir '<private-state-dir>'
```

`_scratch_121_*` run directories, `__pycache__`, and `.venv` are gitignored.
No personal file name, path, or content is printed; personal roots are
compared by hash. Raw transcripts stay in the private state directory.
