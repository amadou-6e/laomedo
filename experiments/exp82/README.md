# Read-only live source check for #82

`live_read_probe.py` uses the existing `gh` login only to fetch Laomedo issue
and native blocker evidence. It takes two independent source snapshots,
compares selected work through the product preflight, and calls the product
GitHub launch entrypoint without a grant authority. The entrypoint must refuse
before any run reservation or stage dispatch. The stage is an assertion trap;
there is no model, credential copy, issue write or Langflow execution.

Run from an installed Laomedo environment with `gh` already authenticated:

```sh
python -m experiments.exp82.live_read_probe
```

The output contains only completeness, comparison and refusal indicators.
The [sanitized observation](observation.json) records the run from committed
probe revision `767fd00` and launch code `edd8252`.
Source content can change between fetches; `stale_unacknowledged` is a valid
safe refusal, while unchanged content should report `source_choice=unchanged`
even when fetch times make snapshot IDs differ. This is a read-only check,
not evidence of a production grant authority or authorized real launch.

## Local zero-turn grant check

The host-side `LocalGrantAuthority` stores one-use grant records in a SQLite
file outside any Git checkout. `laomedo-work-graph issue-grant` reads an
immutable Work Graph snapshot and asks for the selected work key before it
issues a grant. This confirmation does not authenticate an operator. The
grant binds that work key, snapshot ID,
`langflow-local` runner, `stage-launch` scope, expiry, and limits. Redemption
is atomic, so replay refuses. The CLI prints only a grant reference and
nonsecret binding fields. Keep the grant store outside every stage mount.

For the current prototype, the issuer accepts only `--max-turns 0`. A
credential-free pinned-runtime test combines the grant with a saved-flow
stage and a synthetic GitHub source, then verifies one launch and replay
refusal. That first fixture still runs in-process and does not establish
isolation.

The subsequent Docker route runs the stage in the pinned Langflow image with
network disabled, a read-only package and frozen-flow mount, and a tmpfs. The
host keeps the grant ledger, GitHub login and disposable Langflow API token;
the worker receives none of them. The worker reports graph/component hashes
before the host reserves a run, then the host sends one execution command.
The host kills the named container when the granted timeout expires and
retains an `unknown` run with one dispatch attempt. The local CLI exposes
`fetch`, `issue-grant` and `launch` for this zero-turn path.

In a private directory outside Git, the local sequence is:

```sh
laomedo-work-graph fetch --repo amadou-6e/laomedo --output-dir PRIVATE_DIR
laomedo-work-graph inspect SNAPSHOT.json
laomedo-work-graph issue-grant SNAPSHOT.json --work-key WORK_KEY --grant-store PRIVATE_DIR/grants.sqlite --timeout-seconds 30 --max-turns 0
laomedo-work-graph launch SNAPSHOT.json --work-key WORK_KEY --flow-id FLOW_ID --langflow-base http://127.0.0.1:17874 --grant-store PRIVATE_DIR/grants.sqlite --grant-ref GRANT_REF --run-store PRIVATE_DIR/runs.sqlite3 --task TASK
```

Use the snapshot path from `fetch`, the work key from `inspect`, and the grant
reference from `issue-grant`. `launch` prints run and trace IDs plus status, not the flow output
or API token.

Credential-free probes:

```sh
python -m experiments.exp82.docker_stage_probe
python -m experiments.exp82.docker_grant_probe
python -m experiments.exp82.docker_timeout_probe
```

`live_docker_e2e.py` and `live_cli_e2e.py` additionally need a disposable
Langflow 1.12.3 server with auto-login at `127.0.0.1:17874` and the host's
existing read-only `gh` login. They import the no-model flow, fetch the saved
export through the API, re-fetch the live GitHub graph at launch, and run the
Docker worker. Neither probe uses a provider credential, model turn, GitHub
write or production issue task. They print sanitized summaries only.

The local CLI's typed work-key confirmation does not independently
authenticate the operator. The zero-turn restriction and `--network none`
keep this route unsuitable for a real Codex agent. The stage protocol also
has not been audited against malicious component code that forges its stdout
messages. Do not claim hosted, multi-user or untrusted-flow safety from these
tests; #82 retains those boundaries for review.
