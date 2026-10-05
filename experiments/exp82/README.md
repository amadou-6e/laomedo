# Read-only live source check for #82

`live_read_probe.py` uses the existing `gh` login only to fetch Laomedo issue
and native blocker evidence. It takes two independent source snapshots,
compares selected work through the product preflight, and calls the product
GitHub launch entrypoint without a grant authority. The entrypoint must refuse
before any run reservation or stage dispatch. The stage is an assertion trap;
there is no model, credential copy, issue write or Langflow execution.

Run from an installed Laomedo environment with `gh` already authenticated:

```sh
python experiments/exp82/live_read_probe.py
```

The output contains only completeness, comparison and refusal indicators.
Source content can change between fetches; `stale_unacknowledged` is a valid
safe refusal, while unchanged content should report `source_choice=unchanged`
even when fetch times make snapshot IDs differ. This is a read-only check,
not evidence of a production grant authority or authorized real launch.
