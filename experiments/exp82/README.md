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
refusal. The stage still runs in-process in this path, so the test does not
establish an OS boundary around untrusted component code, hard timeout
enforcement, or a live source plus saved-flow API launch. Do not use this
grant path for a model-backed or untrusted flow. Those requirements remain
open under #82.
