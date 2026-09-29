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
| `probe_environment.py` | none (forced-invalid key) | no | SDK/CLI versions, wheel tag, CLI resolution, explicit auth failure, config-dir plumbing |
| `probe_isolation_settings.py` | API key | yes | `setting_sources` control with decoys at both candidate user roots, parent-leak decoys, requested vs effective model/effort, documented-unsupported pair, invalid settings rejection |
| `probe_stream_resume.py` | API key | yes | `ToolUseBlock`/`ToolResultBlock` linkage, resume continuity (marker returned with no Read call), listed-skill invocation, unlisted-skill attempt state, Read reachability, `/name` dispatch of an unlisted skill, explicit failures, `interrupt()` cancellation |

## State directory and isolation boundaries

Both credentialed probes share an existing private `--budget-dir` outside any
git working tree, ideally outside the user folder. Each `--state-dir` must be
a distinct **new or empty** immediate child of that directory. The probes
refuse a non-empty state directory. Fixture and transcript writes stay in the
state directory; the shared spend ledger stays in the private budget directory.
Keep both directories private and never commit them.

The settings probe lays out its run one level down, in `<state>/run/`, and
plants decoys:

- project skill in `<state>/run/project/.claude/skills` (the probe runs with
  `cwd=<state>/run/project`, since Claude looks for project skills in the
  working directory and its parents, never in child folders);
- user skills at **both** candidate roots, `<state>/run/home/.claude/skills`
  and `<state>/run/claude-config/skills`, under different names, so a miss
  identifies which root the runner version actually reads;
- a parent skill and a `CLAUDE.md` in `<state>` itself, a parent of the
  working directory that the probe created. A parent skill seen in
  `system/init` means leakage. `CLAUDE.md` loading is not observable in the
  sanitized stream and is recorded as unobservable. Directories above
  `--state-dir` are not tested.

## Skill checks

Skill runs are classified from the `Skill` call's own result as
`not_attempted`, `attempted_refused`, `attempted_allowed`, or
`attempted_no_result`; errors from other tools do not count. Each fixture
skill's body contains a marker, so a returned marker shows the body actually
ran. The reference says unlisted skills are hidden from the model, so
`not_attempted` is the expected state for the unlisted skill. It also says
`/<name>` dispatch bypasses the allowlist; `unlisted_slash_dispatch` records
whether it did.

The environment hygiene follows #118: the parent process environment reaches
the CLI through the SDK's `env` merge, so `options_env` overrides `HOME`,
`USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `CLAUDE_CONFIG_DIR`, sets
`CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, and blanks every provider-redirecting
variable. The gate refuses to run when any of those variables is set in the
parent environment.

## Credential gate

Both credentialed probes stop before any model call unless the gate passes.
The gate accepts only a dedicated `ANTHROPIC_API_KEY` with the `sk-ant-api`
prefix from the runner environment (subscription OAuth tokens also start with
`sk-ant-` and are refused), rejects a state dir inside a git working
tree, refuses when any provider-redirecting variable is set, rejects an OAuth
token file in the private config dir, and requires reachability of
`api.anthropic.com`, and confirms a runnable Claude CLI before reserving any
model-call budget. Per the SDK docs, `ANTHROPIC_API_KEY` takes precedence over
a subscription login when present. The key prefix is a format check; the
operator must verify that the key is dedicated to this spike.

## Spend

USD 20 is the issue cap. A persistent `issue-121-budget.json` ledger in the
shared budget directory reserves each submitted call before dispatch and
stops after 16 calls or when reserved/observed exposure would reach USD 20.
The intended per-call `max_budget_usd` ceilings sum to USD 12.75 (7 calls at
$0.25, 8 at $1.25, and one at $1.00). Failed calls without a cost report
retain their full reservation. This is a conservative local stop, **not a hard
provider spend cap**: the SDK checks `max_budget_usd` between turns, so one
turn may exceed its ceiling. A strict USD 20 provider cap needs a provider-side
budget. `ResultMessage.total_cost_usd` supplies observed cost when available;
the output also counts calls at submission.

## Observed on the authoring machine (2026-09-29)

`probe_environment.py` ran with `claude-agent-sdk 0.2.161`, Python 3.12.10,
Node v20.11.1, Windows AMD64. The installed distribution is a pure-Python
wheel (`Tag: py3-none-any`), which cannot carry a platform binary, so the SDK
resolved no bundled CLI and no native `claude.exe` is installed: session start
fails with `CLINotFoundError` before any authentication or model call.
Personal roots were unchanged. The two credentialed probes have not been
executed; they require a native `claude.exe` install and a dedicated key.

## Model and effort support

Per the model configuration reference, effort support is model-specific:
Fable 5.x, Opus 5.x/4.7/4.8, and Sonnet 5.x support `low` through `max`;
Opus 4.6 and Sonnet 4.6 support `low` through `max` without `xhigh`; models
not listed do not support effort at all. The supported-pair test therefore
uses `claude-sonnet-4-6` with `low`, and the documented-unsupported case uses
`claude-haiku-4-5` with `low`. The reference documents a silent fallback:
a level the model does not support runs at the highest supported level at or
below it (for example `xhigh` runs as `high` on Opus 4.6).

## Scope limit: conversation versus workspace

The SDK persists conversation history only. Session files live under
`$CLAUDE_CONFIG_DIR/projects/<encoded-cwd>/<session-id>.jsonl`. The stream
probe copies the exact post-run workspace into private state, introduces
drift, verifies that a missing snapshot is refused before modification,
restores the saved workspace and checks its hash **before** resuming in a
fresh query process. This tests a runner-side snapshot guard, not an SDK
workspace feature or a production snapshot registry. Continuity across resume
also requires the synthetic marker to return with no Read call; a re-read is
reported as `run2_reread_file` and does not count as continuity.

## Reproduction

From the Laomedo repository root:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r experiments/feasibility/121/requirements.txt
.venv\Scripts\python experiments/feasibility/121/probe_environment.py
$privateRoot = 'C:\private-laomedo-121' # create privately outside every git tree first
.venv\Scripts\python experiments/feasibility/121/probe_isolation_settings.py --budget-dir $privateRoot --state-dir "$privateRoot\settings"
.venv\Scripts\python experiments/feasibility/121/probe_stream_resume.py --budget-dir $privateRoot --state-dir "$privateRoot\stream"
```

`_scratch_121_*` run directories, `__pycache__`, and `.venv` are gitignored.
Output is sanitized to fixture skill names, structural event fields, and
error classes; arbitrary skill names, tool inputs, and raw error text are not
printed. Personal roots are compared by hash, with `user_projects` labeled
inconclusive because any concurrent Claude Code session changes it. Raw
transcripts stay in the private state directory.
