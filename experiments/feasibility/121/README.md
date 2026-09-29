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

Each credentialed probe requires its own `--state-dir`: a **new or empty**
directory outside any git working tree, ideally outside the user folder. The
probes never delete anything and never write outside `--state-dir`; they
refuse a non-empty directory, so use a different directory per probe.

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
`api.anthropic.com`. Per the SDK docs, `ANTHROPIC_API_KEY` takes precedence
over a subscription login when present.

## Spend

USD 20 is the cap from issue #121. Per-call `max_budget_usd` ceilings sum to
about USD 12.75 worst case (7 calls at $0.25 in the settings probe, 8 at
$1.25 plus one at $1.00 in the stream probe). `max_budget_usd` is checked
between turns, so a single turn can exceed its ceiling. Under an API-key
credential, `ResultMessage.total_cost_usd` is real provider spend; the probes
sum it into `observed_cost_usd` and count a turn on submission as an upper
bound on billable calls.

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
`$CLAUDE_CONFIG_DIR/projects/<encoded-cwd>/<session-id>.jsonl`. Restoring the
last post-run workspace snapshot before a resume is the Laomedo runner
registry's responsibility; `probe_stream_resume.py` fingerprints the workspace
before and after and records the distinction instead of claiming the SDK
provides it. Continuity across resume is verified by a synthetic marker
returning in the resumed run with no Read call; a re-read is reported as
`run2_reread_file` and does not count as continuity.

## Reproduction

From the Laomedo repository root:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r experiments/feasibility/121/requirements.txt
.venv\Scripts\python experiments/feasibility/121/probe_environment.py
.venv\Scripts\python experiments/feasibility/121/probe_isolation_settings.py --state-dir '<new-or-empty-state-dir-1>'
.venv\Scripts\python experiments/feasibility/121/probe_stream_resume.py --state-dir '<new-or-empty-state-dir-2>'
```

`_scratch_121_*` run directories, `__pycache__`, and `.venv` are gitignored.
No personal file name, path, or content is printed; personal roots are
compared by hash, with `user_projects` labeled inconclusive because any
concurrent Claude Code session changes it. Raw transcripts stay in the
private state directory.
