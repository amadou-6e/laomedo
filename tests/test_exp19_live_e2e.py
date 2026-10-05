"""No-model refusal checks for the local EXP-19 run and publisher input."""

from dataclasses import replace
import unittest
from unittest.mock import patch

try:
    from experiments.exp19 import live_e2e
    from experiments.exp19.probe import _graph, _pages
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    live_e2e = None


@unittest.skipUnless(live_e2e is not None, "experiment source is not installed in the wheel")
class LocalExp19Tests(unittest.TestCase):
    def test_changed_issue_is_refused_before_dispatch(self):
        graph = _graph(_pages())
        item = next(item for item in graph.items if item.key == "github:I_2")
        plan = {"issue_signature": live_e2e._issue_signature(graph, item)}
        changed = replace(item, body=item.body + " altered",
                          updated_at="2026-10-02T07:00:00Z")
        with patch.object(live_e2e, "_issue_and_graph", return_value=({}, graph, changed)):
            with self.assertRaisesRegex(ValueError, "selected_issue_changed_before_dispatch"):
                live_e2e._gate(plan)

    def test_artifact_requires_exact_frozen_issue_and_graph_markers(self):
        plan = {"issue_signature": {
            "url": "https://github.com/example/work/issues/2",
            "body_digest": "sha256:" + "a" * 64},
            "graph_snapshot_id": "sha256:" + "b" * 64}
        valid = "\n".join(("# Report", plan["issue_signature"]["url"],
                           plan["issue_signature"]["body_digest"],
                           plan["graph_snapshot_id"], "One testable requirement."))
        live_e2e._validate_artifact(valid.encode(), plan)
        with self.assertRaisesRegex(ValueError, "agent_artifact_missing_frozen_input"):
            live_e2e._validate_artifact(valid.replace("sha256:" + "a" * 64, "missing").encode(), plan)
        with self.assertRaisesRegex(ValueError, "agent_artifact_size_or_encoding_invalid"):
            live_e2e._validate_artifact(valid.encode() + b"\x00", plan)


if __name__ == "__main__":
    unittest.main()
