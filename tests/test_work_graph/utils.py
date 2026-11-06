"""Fresh deterministic source snapshots for Work Graph contract controls."""

import json
from laomedo.work_graph.github import import_pages
from support.paths import repository_root


def make_snapshot():
    """Read the concern-owned source pages and create a fresh immutable snapshot."""
    corpus = json.loads(
        (repository_root() / "tests/test_work_graph/fixtures/corpus.json").read_text(
            encoding="utf-8"
        )
    )
    return import_pages(
        "verify/exp16", corpus["base"], fetched_at="2026-10-05T10:00:00+00:00"
    )
