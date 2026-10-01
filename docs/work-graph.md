# Work Graph foundation

Implementation issue: [#16](https://github.com/amadou-6e/laomedo/issues/16).
Proposed governing specification:
[specs commit 27fe524](https://github.com/amadou-6e/specs/blob/27fe524/projects/laomedo/capabilities/work-graph.md),
under review in [specs PR #152](https://github.com/amadou-6e/specs/pull/152).
The implementation PR remains draft until that contract is reviewed.

## Install and import the synthetic example

Python 3.10 or newer is required. The package has no runtime dependencies.
From the repository root:

```sh
python -m pip install .
laomedo-work-graph import --repo example/work --file examples/work-graph/github-pages.json --output-dir /path/to/private/snapshots
```

The command returns a JSON summary with `snapshot_id`, artifact path,
`source_complete`, and item/edge counts. The example contains a closed
prerequisite, its open dependent, and an isolated open item. Use the returned
path to inspect the snapshot:

```sh
laomedo-work-graph inspect /path/to/private/snapshots/HASH.json --state open --label notes
```

The isolated notes item remains in `items` even though it has no edges.
`dependencies` contains edges with two matched endpoints;
`context_dependencies` preserves prerequisites outside the selected projection.
The state/label selection does not change the readiness values calculated
from the complete stored graph. Repeated labels select their union.

## Fetch repository work

```sh
gh auth status
laomedo-work-graph fetch --repo OWNER/REPO --output-dir /path/to/private/snapshots
```

The connector calls `gh api graphql` using the existing gh account. It reads
issues across all states, follows repository issue pagination, and requests
native `blockedBy` and `blocking` relationships. It never reads the gh token
into Laomedo records. Source issue bodies are retained, so snapshots belong in
an appropriate private data directory outside Git.

Each issue uses its stable GitHub ID with a `github:` prefix. Repository,
number, source URL, update time, labels, and exact fetched body remain in the
snapshot. Endpoint-only references retain their stable IDs, repository names,
URLs, and native relationship provenance. They remain unresolved until a full
item snapshot is available. The initial connector imports one repository;
cross-repository resolution is a subsequent extension.

The dependency connections are capped at 100 entries per issue and labels
at 100. If totals exceed returned counts, the snapshot explicitly reports
incompleteness and warning codes; it does not claim a complete dependency
inventory. A failed later page preserves already fetched items with an
incomplete marker. A failed first page returns an error. Repeated cursors,
conflicting issue versions, and responses for a different repository fail.
Fetching live mutable GitHub data is not a transaction: update markers and
fetch time identify observed data, not an atomic GitHub revision.

## Evidence and readiness

Snapshots use canonical JSON SHA-256 identity, including fetch time and
connector/schema versions. Each refresh writes a new artifact. Reading checks
the digest; writing refuses conflicting bytes at an existing artifact path.
Digest verification detects content changes but is not a signed authenticity
claim. Current schema and connector versions are `1` and `github-gh-v1`.

Readiness values describe source evidence:

- `closed`: the fetched issue state is closed.
- `cyclic`: the open item belongs to a dependency cycle, including self loops.
- `unknown`: the source is incomplete, blocker inventory is incomplete, or
  a prerequisite has no complete item record.
- `blocked`: at least one fetched prerequisite remains open.
- `ready`: the source is complete and all known prerequisites are closed.

The first implementation treats any incomplete source inventory conservatively
for all open items. It exposes warning codes so future consumers can explain
that decision. `ready` is not authorization to execute, and source closure is
not acceptance evidence for an agent result. UI controls, agent launch,
automatic scheduling, issue write-back and code merging are outside this slice.

## Verification

```sh
python -m unittest discover -s tests -v
```

Tests cover hash round trips/tamper, retained refresh artifacts, stable identity,
isolated filters, hidden blockers, closed prerequisites, unresolved external
references, truncated inventories, cycles versus downstream blocked items,
pagination and interrupted fetching. CI builds and installs the wheel before
testing, without adding `src` to Python's import path, then imports the synthetic
example through the installed CLI. No model call is needed.

The initial local check on 2026-10-01 passed all 12 tests against the installed
wheel. A live fetch of `amadou-6e/theseo-anysearch` followed three issue pages
and captured 260 issues and 24 native dependencies with `source_complete=true`.
The open projection contained 75 issues, 23 matched edges and one prerequisite
context edge; source readiness was 58 ready, 16 blocked and one unknown.
The captured snapshot ID was
`sha256:1cb968e78fe86e66b0948a759e168f50aa0872ed1a74d1350e993ae72cabbf6b`.
Those are observations at fetch time, not fixed repository totals; raw issue
bodies and generated snapshots remain outside Git.
