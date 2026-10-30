# Python formatting

Black is the Python formatter for the entire maintained project. Its exact
version, Python 3.10 syntax target and 88-character line length are configured
in `pyproject.toml`. Preview and unstable styles are disabled.

Install with `python -m pip install -e '.[dev]'` or `uv sync --extra dev`.
From the repository root, run `python -m black .` to format and
`python -m black --check --diff --no-cache .` to check. The
`Python formatting / black` GitHub Actions job runs the latter command on every
push and pull request, after checking file-discovery and archive-preservation
regressions. Both commands use the same configuration and file discovery.

The scope includes `src/`, `components/`, `docker/`, `examples/`, `tests/`,
`tools/` and unsealed experiment helpers. Newly added Python files are included
without adding a path to CI. Black respects `.gitignore` for local virtual
environments, caches, generated build output and private state. It formats
Python files, not JavaScript, Markdown, patch payloads, embedded code strings
or immutable JSON graph/execution exports.

## Exact historical exceptions

The existing [migration policy](package-layout.md#one-time-migration)
requires preserving historical execution evidence. A tracked-file audit at
`4b46032` found the following seven archived experiment sources whose current
bytes still match SHA-256 values in retained evidence. `force-exclude` protects
only these exact paths, including when an editor passes them explicitly.
Existing evidence is not rewritten or resealed, and no experiment directory
or future file is exempted as a whole. Other historical manifests describe
their original revision; formatting current maintained copies does not
update or revalidate those older runs.

| Archived Python source | Retained evidence |
| --- | --- |
| [experiments/exp100/bundle_transfer.py](../../experiments/exp100/bundle_transfer.py) | [experiments/exp100/observation-s3.json](../../experiments/exp100/observation-s3.json) |
| [experiments/exp100/probe_s4_bundle.py](../../experiments/exp100/probe_s4_bundle.py) | [experiments/exp100/observation-s4-03.json](../../experiments/exp100/observation-s4-03.json) |
| [experiments/exp100/probe_s4_diag.py](../../experiments/exp100/probe_s4_diag.py) | [experiments/exp100/observation-s4-02.json](../../experiments/exp100/observation-s4-02.json) |
| [experiments/exp100/probe_stage_s8.py](../../experiments/exp100/probe_stage_s8.py) | [experiments/exp100/observation-s8.json](../../experiments/exp100/observation-s8.json) |
| [experiments/exp139/run_flow.py](../../experiments/exp139/run_flow.py) | [experiments/exp139/DEMO-MANIFEST.json](../../experiments/exp139/DEMO-MANIFEST.json), [experiments/exp139/MANIFEST.json](../../experiments/exp139/MANIFEST.json) |
| [experiments/exp139/verifier_control.py](../../experiments/exp139/verifier_control.py) | [experiments/exp139/DEMO-MANIFEST.json](../../experiments/exp139/DEMO-MANIFEST.json), [experiments/exp139/MANIFEST.json](../../experiments/exp139/MANIFEST.json) |
| [experiments/feasibility/agent-observability/analyze.py](../../experiments/feasibility/agent-observability/analyze.py) | [experiments/feasibility/agent-observability/host-analysis.json](../../experiments/feasibility/agent-observability/host-analysis.json) |

Exact source digests are recorded in
[`tools/formatting/historical-sources.json`](../../tools/formatting/historical-sources.json)
and checked by `tests/test_formatting_policy.py`. Create a maintained copy if
one of these campaigns needs further development; retain the sealed original.
Do not add exclusions or `fmt: off` blocks to bypass formatting maintained code.

## Updating the formatter

Update the `dev` extra pin and `[tool.black].required-version` together, run
`uv lock`, then format and check the repository. Keep the formatting update
separate from behavior changes. A green formatter check establishes style
compliance; it does not establish real-agent, graph or browser acceptance.
