"""Credential-free issue source, using the production context parser."""
import hashlib
import json
from lfx.custom.custom_component.component import Component
from lfx.io import Output, StrInput
from lfx.schema import Data, Message
from laomedo.issue_context import fetch_context


class FixtureIssue(Component):
    display_name = "Fixture issue snapshot"
    description = "Frozen fixture only. Never reads ambient GitHub credentials."
    name = "FixtureIssue"
    inputs = [StrInput(name="issue_json", display_name="Fixture issue JSON", required=True)]
    outputs = [Output(name="task", display_name="Task", method="task_output", group_outputs=True),
               Output(name="snapshot", display_name="Frozen issue", method="snapshot_output", group_outputs=True)]

    def _snapshot(self):
        fixture = json.loads(self.issue_json)
        issue = fixture["issue"]
        repository = fixture["repository"]
        number = issue["number"]
        def request(path):
            if path == f"repos/{repository}/issues/{number}":
                return issue
            if path == f"repos/{repository}/issues/{number}/timeline?per_page=100&page=1":
                return []
            raise ValueError("fixture_request_outside_allowlist")
        context = fetch_context(repository, number, request=request,
                                fetched_at=fixture["fetched_at"])
        canonical = json.dumps(context, sort_keys=True, separators=(",", ":")).encode()
        return {"source": "fixture", "context": context,
                "snapshot_id": "sha256:" + hashlib.sha256(canonical).hexdigest(),
                "body_sha256": hashlib.sha256(issue["body"].encode()).hexdigest()}

    def snapshot_output(self) -> Data:
        return Data(data=self._snapshot())

    def task_output(self) -> Message:
        snapshot = self._snapshot()
        return Message(text=json.dumps({"task": "Implement fixture issue; submit the configured output form. Do not publish.",
                                        "frozen_issue": snapshot}, sort_keys=True))
