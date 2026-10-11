"""Credential-free schema, host precheck and final evaluator agreement."""

from copy import deepcopy
import io
import json
import queue
import unittest

from laomedo.output_contract import (requirements, evaluate, evaluate_envelope,
                                    verify_requirements, precheck_response, dynamic_tool)
from laomedo.local_runner import AppServer


FORM = {"schema_version": 1, "fields": [{"name": "report", "type": "string",
        "required": True, "checks": {"nonempty": True, "max_length": 32}}]}


class OutputContractTests(unittest.TestCase):
    def test_pin_is_canonical_and_changed_requirements_change_revision(self):
        pin = requirements(FORM)
        self.assertEqual(pin, requirements(json.loads(json.dumps(FORM, sort_keys=True))))
        changed = deepcopy(FORM)
        changed["fields"][0]["checks"]["max_length"] = 31
        self.assertNotEqual(pin["requirements_revision"], requirements(changed)["requirements_revision"])
        pin["requirements"]["fields"][0]["checks"]["max_length"] = 30
        with self.assertRaisesRegex(ValueError, "revision_mismatch"):
            verify_requirements(pin)

    def test_valid_failure_is_form_valid_and_identity_preserved(self):
        pin = requirements(FORM)
        envelope = {"schema_version": "laomedo.agent-submission.v1", "submission": {
            "report": "could not implement", "task_outcome": "failure"},
            "task_outcome": "failure", "executor_status": "completed",
            "requirements_revision": pin["requirements_revision"], "run_reference": {"run_id": "test"}}
        result = evaluate_envelope(pin, envelope)
        self.assertEqual(result["contract_status"], "accepted")
        self.assertEqual(result["agent_submission"], envelope)

    def test_invalid_data_is_never_echoed_in_rejection(self):
        pin = requirements(FORM)
        result = evaluate(pin, {"report": "secret-token-that-is-longer-than-thirty-two-characters"})
        self.assertEqual(result["errors"], [{"path": "/report", "code": "max_length"}])
        self.assertNotIn("secret-token", json.dumps(result))
        for submission, code in (({}, "required"), ({"report": "  "}, "nonempty"),
                                 ({"report": 12}, "type_mismatch"), (None, "object_required")):
            self.assertEqual(evaluate(pin, submission)["errors"][0]["code"], code)

    def test_unknown_executable_schema_checks_and_nonfinite_values_refused(self):
        for invalid in ({"schema_version": 1, "fields": [], "script": "print(1)"},
                        {"schema_version": 1, "fields": [{"name": "x", "type": "number", "checks": {"minimum": float("nan")}}]},
                        {"schema_version": 1, "fields": [{"name": "x", "type": "string", "checks": {"command": "echo"}}]}):
            with self.assertRaises(ValueError):
                requirements(invalid)
        self.assertEqual(evaluate(requirements(FORM), {"report": float("inf")})["errors"][0]["code"], "invalid_json_value")

    def test_typed_numeric_enum_and_size_checks(self):
        pin = requirements({"schema_version": 1, "fields": [
            {"name": "n", "type": "integer", "checks": {"minimum": 1, "maximum": 2}},
            {"name": "b", "type": "boolean", "checks": {"enum": [True]}},
            {"name": "a", "type": "array", "checks": {"min_length": 1, "max_length": 2}}]})
        self.assertEqual(evaluate(pin, {"n": True, "b": False, "a": []})["errors"], [
            {"path": "/n", "code": "type_mismatch"}, {"path": "/b", "code": "enum"}, {"path": "/a", "code": "min_length"}])

    def test_reserved_task_outcome_requires_exact_enum_if_declared(self):
        for field in ({"name": "task_outcome", "type": "string"},
                      {"name": "task_outcome", "type": "boolean", "checks": {"enum": ["success", "failure"]}},
                      {"name": "task_outcome", "type": "string", "checks": {"enum": ["success", "unknown"]}}):
            with self.assertRaisesRegex(ValueError, "reserved_task_outcome"):
                requirements({"schema_version": 1, "fields": [field]})

    def test_native_precheck_and_final_validation_apply_identical_requirements(self):
        pin = requirements(FORM)
        app = AppServer.__new__(AppServer)
        app.events, app.output_requirements, app.active_thread_id = [], pin, "thread"
        app.process = type("Process", (), {"stdin": io.StringIO()})()
        for index, submission in enumerate(({}, {"report": "valid"})):
            app._observe({"id": index, "method": "item/tool/call", "params": {
                "threadId": "thread", "turnId": "turn", "callId": str(index),
                "namespace": None, "tool": "laomedo_output_precheck", "arguments": {
                    "requirements_revision": pin["requirements_revision"], "submission": submission}}})
        replies = [json.loads(line) for line in app.process.stdin.getvalue().splitlines()]
        self.assertEqual(json.loads(replies[0]["result"]["contentItems"][0]["text"]), evaluate(pin, {}))
        self.assertEqual(json.loads(replies[1]["result"]["contentItems"][0]["text"]), evaluate(pin, {"report": "valid"}))
        self.assertEqual(dynamic_tool(pin)["type"], "function")

    def test_native_binding_mismatch_and_final_pin_mismatch_rejected(self):
        pin = requirements(FORM)
        response = precheck_response(pin, {"threadId": "wrong", "tool": "laomedo_output_precheck"}, "thread")
        self.assertIn("precheck_binding_mismatch", response["contentItems"][0]["text"])
        self.assertEqual(evaluate_envelope(pin, {"schema_version": "laomedo.agent-submission.v1",
            "submission": {"report": "valid"}, "requirements_revision": "wrong"})["contract_status"], "rejected")

    def test_contradictory_task_outcome_does_not_validate(self):
        pin = requirements(FORM)
        for reported, claimed in (("failure", "success"), ({"invalid": True}, "success")):
            result = evaluate_envelope(pin, {"schema_version": "laomedo.agent-submission.v1",
                "requirements_revision": pin["requirements_revision"], "executor_status": "completed",
                "submission": {"report": "valid", "task_outcome": reported}, "task_outcome": claimed})
            self.assertEqual(result["errors"][0]["code"], "task_outcome_mismatch")

    def test_native_request_queue_answers_precheck_before_turn_ack(self):
        pin = requirements(FORM)
        app = AppServer.__new__(AppServer)
        app.seq, app.events, app.messages = 0, [], queue.Queue()
        app.output_requirements, app.active_thread_id = pin, "thread"
        app.process = type("Process", (), {"stdin": io.StringIO(), "poll": lambda _: None})()
        app.messages.put({"id": "server-request", "method": "item/tool/call", "params": {
            "threadId": "thread", "turnId": "turn", "callId": "call",
            "namespace": None, "tool": "laomedo_output_precheck", "arguments": {
                "requirements_revision": pin["requirements_revision"], "submission": {}}}})
        app.messages.put({"id": 1, "result": {"turn": {"id": "turn"}}})
        response = app.request("turn/start", {"threadId": "thread"})
        self.assertEqual(response["result"]["turn"]["id"], "turn")
        lines = [json.loads(line) for line in app.process.stdin.getvalue().splitlines()]
        self.assertEqual(lines[1]["id"], "server-request")
        self.assertIn('"code":"required"', lines[1]["result"]["contentItems"][0]["text"])
        self.assertEqual(app.precheck_call_count, 1)
