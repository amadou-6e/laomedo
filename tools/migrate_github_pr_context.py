"""Explicitly upgrade compatible saved PR ports; refuse ambiguous graph wiring."""

import argparse
import json
from pathlib import Path
from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template
from laomedo.integrations.langflow.pr_context.migration import migrate_pr_graph


def main():
    """Read a caller-selected graph, migrate copies and write only a new output file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(
            "Choose a new output file; the original graph is never overwritten."
        )
    code = (
        Path(__file__).resolve().parents[1] / "components/laomedo/github_pr.py"
    ).read_text(encoding="utf-8")
    definition, _ = build_custom_component_template(Component(_code=code))
    try:
        result = migrate_pr_graph(
            json.loads(args.source.read_text(encoding="utf-8")), definition
        )
    except ValueError:
        parser.error("PR connections require manual repair; no output was written.")
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
