# Issue 120: Codex runner isolation, persistence, and settings

Probes for [specs issue #120](https://github.com/amadou-6e/specs/issues/120).
They verify the #119 skill-discovery baseline against the pinned runner version
and investigate whether Codex can run as a persistent Laomedo flow step.

## Requirements

- Python 3.9 or newer (stdlib only; no pip dependencies). The observed run used
  Python 3.12.10.
- Codex CLI binary. The observed Windows binary was
  `codex-cli 0.155.0-alpha.16.3`, SHA-256
  `589f2546cc1e86703da326b00741f8b7a58fd182a1a90499faa0beebf22a24e2`.
  The probes record the runtime version via `codex --version` and
  `thread.cliVersion`. No Codex SDK is imported.
- `_shared.py` is the app-server client. It buffers notifications, uses unique
  request ids, raises a typed timeout, and records the version. Each connection
  writes its unredacted server stream to a uniquely named JSONL file in its
  private state directory for inspection; those files must never be committed.

## Probes

| Probe | Credential | Model call | What it tests |
| --- | --- | --- | --- |
| `probe_model_effort.py` | none | no | model/list efforts, requested supported pair, runner-side rejection of unknown model and invalid or unsupported effort; thread-start effective model |
| `probe_isolation.py` | none | no | private skill discovery, `instructionSources` leak check, personal root comparison |
| `probe_persistence.py` | private ChatGPT handoff | yes | completed turn, frozen post-run workspace, drift and restore before `thread/resume`, missing-snapshot refusal, `thread/list`, unknown-thread rejection |
| `probe_stream_events.py` | private ChatGPT handoff | yes | raw item notifications, matching `item/started` and terminal `item/completed` tool result, usage-event count |

`probe_model_effort.py` is unauthenticated by construction and submits no
`turn/start`. A local run against the observed CLI found that it accepted an
unknown model at `thread/start` and an invalid effort at `turn/start`, so the
runner must validate both against `model/list` before dispatch. The corrected
probe tests that validation and chooses a model with a narrower effort set to
exercise valid-but-unsupported rejection. Effective per-turn effort and no
silent downgrade still need a completed credentialed turn. The credentialed
probes read the matching private rollout `turn_context` when available.

Both credentialed probes print the accumulated summary even when a request
times out after a turn was submitted, so a paid turn is never lost without
evidence; an attempted turn counts toward the model-call total either way.

## Credential gate

For this single-user feasibility spike, `provision_chatgpt_handoff.py` copies
only the current file-backed ChatGPT `auth.json` into one persistent private
Codex profile. Create an access-restricted state directory outside every Git
working tree first. Provision **once**; the script refuses to overwrite an
existing private auth file. Reuse that same directory for all #120 tests so
Codex can refresh its private copy in place. Do not recopy from the personal
profile before each test. This is a temporary approach until #129 defines
the production login flow.

Both credentialed probes use the same gate and stop before any model call when
it fails. The ChatGPT handoff gate:

- requires file-backed **ChatGPT** mode as reported by `codex login status`;
- rejects a `--state-dir` inside a git working tree;
- requires TCP reachability to `chatgpt.com:443`,
  as a prerequisite (not a guarantee of an authenticated request).

The provisioning script copies the credential once but never prints its value.
No credential, session, or raw trace is committed. A private copy can refresh
independently and may invalidate the original interactive login. Keep the
private profile persistent and inspect the personal login if a refresh occurs.
The API-key mode remains available with `--credential-mode api_key` and a
dedicated `--credential-ref`, but is not required for this temporary spike.

## Spend

The model-backed probes prefer advertised `gpt-6-luna` with low effort, then
fall back to an advertised supported pair. One private `turn-budget.json`
allows at most three submitted turns across both probes, counting a timeout as
an attempt. A ChatGPT subscription run has no direct API dollar charge; record
token usage and an API-equivalent estimate separately, without calling it
actual spend. An API-key run has real provider spend and still requires the
USD 20 limit from #120.

## Scope limit: workspace snapshots

Codex has no concept of a Laomedo workspace snapshot. The spike copies and
hashes the post-run disposable workspace, introduces a synthetic drift file,
restores the snapshot, and resumes only if the restored hash matches. It also
checks that a missing snapshot fails before the workspace changes. This proves
the spike's guard and native resume sequence, not a production session registry
or remote persistence.

## Reproduction

From the Laomedo repository root:

```powershell
python experiments/feasibility/120/probe_model_effort.py --codex '<absolute-path-to-codex>'
python experiments/feasibility/120/probe_isolation.py --codex '<absolute-path-to-codex>'
python -m unittest discover -s experiments/feasibility/120 -p 'test_*.py' -v
python experiments/feasibility/120/provision_chatgpt_handoff.py --state-dir '<private-state-dir>'  # once
python experiments/feasibility/120/probe_persistence.py --codex '<absolute-path-to-codex>' --state-dir '<private-state-dir>'
python experiments/feasibility/120/probe_stream_events.py --codex '<absolute-path-to-codex>' --state-dir '<private-state-dir>'          # preflight
python experiments/feasibility/120/probe_stream_events.py --codex '<absolute-path-to-codex>' --state-dir '<private-state-dir>' --run    # one turn
```

`_scratch_120_*` run directories and `__pycache__` are gitignored. No personal
file name, path, or content is printed; personal roots are compared by hash.
