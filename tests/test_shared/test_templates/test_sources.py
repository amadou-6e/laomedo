"""Current source/hash and full non-source graph invariants, not graph execution."""

from support.paths import repository_root

from hashlib import sha256
import json
from pathlib import Path
import unittest

ROOT = repository_root()


class ComponentTemplateTests(unittest.TestCase):
    def test_canonical_sources_hashes_and_all_other_graph_values(self):
        contract = json.loads(
            (ROOT / "tests/contracts/component-templates.json").read_text()
        )
        self.assertTrue(contract["files"])
        for record in contract["files"]:
            with self.subTest(graph=record["path"]):
                graph = json.loads((ROOT / record["path"]).read_text(encoding="utf-8"))
                nodes = {
                    n["id"]: n
                    for n in graph.get("nodes", graph.get("data", {}).get("nodes", []))
                }
                for item in record["nodes"]:
                    definition = nodes[item["node_id"]]["data"]["node"]
                    source = (ROOT / item["component"]).read_text(encoding="utf-8")
                    self.assertEqual(definition["template"]["code"]["value"], source)
                    self.assertEqual(
                        "code_hash" in definition.get("metadata", {}),
                        item["has_code_hash"],
                    )
                    if item["has_code_hash"]:
                        self.assertEqual(
                            definition["metadata"]["code_hash"],
                            sha256(source.encode()).hexdigest()[:12],
                        )
                        definition["metadata"]["code_hash"] = "CURRENT_COMPONENT_HASH"
                    definition["template"]["code"]["value"] = "CURRENT_COMPONENT_SOURCE"
                self.assertEqual(
                    sha256(
                        json.dumps(
                            graph,
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                        ).encode()
                    ).hexdigest(),
                    record["graph_values_sha256"],
                )
