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
| `probe_persistence.py` | API key | yes | completed turn, frozen post-run workspace, drift and restore before `thread/resume`, missing-snapshot refusal, `thread/list`, unknown-thread rejection |
| `probe_stream_events.py` | API key | yes | raw item notifications, matching `item/started` and terminal `item/completed` tool result, usage-event count |

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

Both credentialed probes use the same gate and stop before any model call when
it fails. The gate:

- requires a declared dedicated secret-store reference, rejects an exact copy
  of the personal `auth.json`, and accepts only **API-key** mode as reported by
  `codex login status`. The reference is a provisioning declaration, not
  cryptographic proof of who owns the API key. A reviewer must verify that the
  reference belongs to a dedicated Laomedo credential before running;
- rejects a copied personal **ChatGPT** login, per the #120 rule and the #119
  statement that its ChatGPT-auth exception does not extend to #120. This also
  blocks a dedicated ChatGPT service-account token, which #119 listed as a
  production option; that is a conservative choice for this spike, not a claim
  that service accounts are unsuitable;
- rejects a `--state-dir` inside a git working tree;
- requires TCP reachability to `api.openai.com:443`, the API-key traffic host,
  as a prerequisite (not a guarantee of an authenticated request).

No credential value, session, or raw trace leaves the private state directory.
The CLI's credential material must be provisioned into that directory by the
runner's secret store outside this repository; these scripts never copy a
login or key. The preflight is deliberately fail-closed when no reference or
auth file is present.

## Spend

The paid probes prefer advertised `gpt-6-luna` with low effort to keep the
bounded calls inexpensive, then fall back to an advertised supported pair.
The USD 20 cap is set by issue #120. Because the gate admits only an API-key
credential, spend is real provider spend, not an API-equivalent estimate from a
ChatGPT subscription. Track it from the provider's usage dashboard and from the
token-usage event count the stream probe records. The raw usage counters
remain in private state; a sanitized count alone does not calculate cost.
A ChatGPT-authenticated run would
not be billed in dollars and is out of scope for this spike.

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
python experiments/feasibility/120/probe_persistence.py --codex '<absolute-path-to-codex>' --state-dir '<private-state-dir>' --credential-ref '<secret-store-reference>'
python experiments/feasibility/120/probe_stream_events.py --codex '<absolute-path-to-codex>' --state-dir '<private-state-dir>' --credential-ref '<secret-store-reference>'          # preflight
python experiments/feasibility/120/probe_stream_events.py --codex '<absolute-path-to-codex>' --state-dir '<private-state-dir>' --credential-ref '<secret-store-reference>' --run    # model turn
```

`_scratch_120_*` run directories and `__pycache__` are gitignored. No personal
file name, path, or content is printed; personal roots are compared by hash.
