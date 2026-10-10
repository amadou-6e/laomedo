"""Real pinned Langflow component inputs and outputs, without provider traffic."""

import importlib.util
import json
import sys
from pathlib import Path
import unittest

from lfx.schema import Data
from laomedo.output_contract import requirements

PATH = Path(__file__).resolve().parents[2] / "components/laomedo/output_contract.py"
SPEC = importlib.util.spec_from_file_location("laomedo_output_contract_component", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
FORM = {"schema_version": 1, "fields": [
    {"name": "task_outcome", "type": "string", "required": True, "checks": {"enum": ["success", "failure"]}},
    {"name": "report", "type": "string", "required": True, "checks": {"nonempty": True}}]}


class OutputContractComponentTests(unittest.TestCase):
    def node(self, submission, outcome="success", revision=None):
        node = MODULE.LaomedoOutputContract()
        node.requirements_json = json.dumps(FORM)
        node.agent_submission = Data(data={"schema_version": "laomedo.agent-submission.v1",
            "submission": submission, "task_outcome": outcome, "executor_status": "completed",
            "run_reference": {"run_id": "synthetic"},
            "requirements_revision": revision or requirements(FORM)["requirements_revision"]})
        return node

    def test_ports_are_grouped_and_final_evaluation_preserves_outcome(self):
        self.assertEqual([port.name for port in MODULE.LaomedoOutputContract.outputs], ["requirements", "validation"])
        for outcome in ("success", "failure"):
            node = self.node({"task_outcome": outcome, "report": "fixture"}, outcome)
            result = node.validation_output().data
            self.assertEqual(result["contract_status"], "accepted")
            self.assertEqual(result["agent_submission"]["task_outcome"], outcome)
            self.assertEqual(node.requirements_output().data, requirements(FORM))

    def test_invalid_submission_is_rejected_without_execution_error(self):
        result = self.node({"task_outcome": "success"}).validation_output().data
        self.assertEqual(result["contract_status"], "rejected")
        self.assertEqual(result["errors"], [{"path": "/report", "code": "required"}])

    def test_changed_downstream_contract_rejects_precheck_pin(self):
        result = self.node({"task_outcome": "success", "report": "fixture"}, revision="sha256:" + "a" * 64).validation_output().data
        self.assertEqual(result["errors"][0]["code"], "requirements_revision_mismatch")

    def test_configuration_error_is_build_error(self):
        node = self.node({})
        node.requirements_json = '{"schema_version":1,"fields":[],"command":"echo"}'
        with self.assertRaises(ValueError):
            node.requirements_output()
