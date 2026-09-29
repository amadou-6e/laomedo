# Issue 120: Codex runner isolation, persistence, and settings

Probes for [specs issue #120](https://github.com/amadou-6e/specs/issues/120).
They verify the #119 skill-discovery baseline against the pinned runner version
and investigate whether Codex can run as a persistent Laomedo flow step.

## Requirements

- Python 3.9 or newer (stdlib only; no pip dependencies).
- Codex CLI binary. The probes record the exact version via `codex --version`.
- `_shared.py` is the app-server client. It buffers notifications, uses unique
  request ids, raises a typed timeout, and records the version.

## Probes

| Probe | Credential | Model call | What it tests |
| --- | --- | --- | --- |
| `probe_model_effort.py` | none | no | model/list efforts, effective values from `thread/start`, invalid and valid-but-unsupported effort rejection, unknown model rejection |
| `probe_isolation.py` | none | no | private skill discovery, `instructionSources` leak check, personal root comparison |
| `probe_persistence.py` | API key | yes | `thread/resume` after restart, `thread/list`, unknown-thread rejection, resume from a different cwd |
| `probe_stream_events.py` | API key | yes | raw item notifications, tool call with matching result, usage |

`probe_model_effort.py` is unauthenticated by construction: the scratch profile
has no credential and the constructed environment carries none, so a dispatched
turn cannot spend. It calls `turn/start` for the rejection checks only. The
"no silent downgrade" half of condition 5 needs a credentialed probe and is not
claimable from this script.

Both credentialed probes print the accumulated summary even when a request
times out after a turn was submitted, so a paid turn is never lost without
evidence; an attempted turn counts toward the model-call total either way.

## Credential gate

Both credentialed probes use the same gate and stop before any model call when
it fails. The gate:

- accepts only a dedicated **API-key** credential (`codex login status`
  reports API-key mode);
- rejects a copied personal **ChatGPT** login, per the #120 rule and the #119
  statement that its ChatGPT-auth exception does not extend to #120. This also
  blocks a dedicated ChatGPT service-account token, which #119 listed as a
  production option; that is a conservative choice for this spike, not a claim
  that service accounts are unsuitable;
- rejects a `--state-dir` inside a git working tree;
- requires TCP reachability to `api.openai.com:443`, the API-key traffic host,
  as a prerequisite (not a guarantee of an authenticated request).

No credential value, session, or raw trace leaves the private state directory.

## Spend

The USD 20 cap is set by issue #120. Because the gate admits only an API-key
credential, spend is real provider spend, not an API-equivalent estimate from a
ChatGPT subscription. Track it from the provider's usage dashboard and from the
token-usage events the stream probe records. A ChatGPT-authenticated run would
not be billed in dollars and is out of scope for this spike.

## Scope limit: workspace snapshots

Codex has no concept of a Laomedo workspace snapshot. `probe_persistence.py`
records what Codex does on resume (same thread id, and behavior when the cwd
changes or the thread id is unknown). The refusal to resume when the last
post-run snapshot is missing belongs to the Laomedo runner's session registry,
not to Codex, and cannot be demonstrated by this probe alone.

## Reproduction

From the Laomedo repository root:

```powershell
python experiments/feasibility/120/probe_model_effort.py --codex '<absolute-path-to-codex>'
python experiments/feasibility/120/probe_isolation.py --codex '<absolute-path-to-codex>'
python experiments/feasibility/120/probe_persistence.py --codex '<absolute-path-to-codex>' --state-dir '<private-state-dir>'
python experiments/feasibility/120/probe_stream_events.py --codex '<absolute-path-to-codex>' --state-dir '<private-state-dir>'          # preflight
python experiments/feasibility/120/probe_stream_events.py --codex '<absolute-path-to-codex>' --state-dir '<private-state-dir>' --run    # model turn
```

`_scratch_120_*` run directories and `__pycache__` are gitignored. No personal
file name, path, or content is printed; personal roots are compared by hash.
