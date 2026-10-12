"""Known embedded legacy exports migrate explicitly without rewiring."""
import importlib.util
import json
from pathlib import Path
import unittest
from test_workgraph_demo import run_case, records

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("legacy_migration", ROOT / "examples/langflow-contract-routing/migrate_legacy.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def original():
    flow = json.loads((ROOT / "examples/langflow-workgraph-demo/flow.json").read_text())
    for node in flow["data"]["nodes"]:
        if node["data"]["type"] == "LaomedoOutputContractLegacy":
            node["data"]["type"] = "LaomedoOutputContract"
            code = node["data"]["node"]["template"]["code"]["value"]
            node["data"]["node"]["template"]["code"]["value"] = code.replace("LaomedoOutputContractLegacy", "LaomedoOutputContract").replace("Laomedo Output Contract (legacy)", "Laomedo Output Contract")
    return flow


class MigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_migrated_export_preserves_form_and_routes(self):
        before = original()
        after = migration.migrate(before)
        self.assertEqual(before, original(), "input must not be mutated")
        self.assertEqual([(e["id"], e["source"], e["target"], e["data"]["sourceHandle"]["name"], e["data"]["targetHandle"]["fieldName"]) for e in before["data"]["edges"]],
                         [(e["id"], e["source"], e["target"], e["data"]["sourceHandle"]["name"], e["data"]["targetHandle"]["fieldName"]) for e in after["data"]["edges"]])
        for node in after["data"]["nodes"]:
            if node["id"] in ("requirements", "contract"):
                self.assertEqual(node["data"]["type"], "LaomedoOutputContractLegacy")
                self.assertEqual(node["data"]["node"]["template"]["requirements_json"]["value"], next(n for n in before["data"]["nodes"] if n["id"] == node["id"])["data"]["node"]["template"]["requirements_json"]["value"])
        result, calls = await run_case({"task_outcome":"success", "report":"migration fixture"}, flow_payload=after)
        self.assertEqual(len(calls), 1)
        self.assertEqual([r["destination"] for r in records(result)], ["success"])
        self.assertEqual(migration.migrate(after), after)

    async def test_unknown_embedded_source_refuses(self):
        flow = original()
        node = next(n for n in flow["data"]["nodes"] if n["id"] == "contract")
        node["data"]["node"]["template"]["code"]["value"] += "\n# unknown modification\n"
        with self.assertRaisesRegex(ValueError, "unsupported_legacy_contract_source"):
            migration.migrate(flow)
