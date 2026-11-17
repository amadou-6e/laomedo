"""Real isolated app/agent proposals; approvals are explicit app requests in this harness."""

import json
import gzip
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4

ROOT = Path("C:/CodeWorkspace/laomedo")
META = json.loads((ROOT / ".tools/assistant-291-live.json").read_text())
BASE = META["base"]
sys.path.insert(0, str(ROOT / ".tools/worktrees/assistant-291/src"))
from laomedo.integrations.langflow.assistant.catalog import ComponentCatalog
from laomedo.integrations.langflow.assistant.models import (
    DraftGraph,
    DraftNode,
    DraftEdge,
)


class Acceptance:
    def __init__(self):
        deadline = time.monotonic() + 90
        while True:
            try:
                self.call("/health")
                break
            except (urllib.error.URLError, ConnectionError):
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
        self.token = self.call("/api/v1/auto_login")["access_token"]
        (Path(META["state"]) / "acceptance-session.json").write_text(
            json.dumps({"token": self.token})
        )

    def call(self, path, body=None):
        headers = {"Content-Type": "application/json", "Origin": BASE}
        if hasattr(self, "token"):
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(
            BASE + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            data = response.read()
            if response.headers.get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            return json.loads(data)

    def run(self):
        catalog = self.call("/api/v1/all")
        metadata = ComponentCatalog(catalog)
        candidates = metadata.search("Chat Input")["components"]
        incoming = next(
            v["component_type"]
            for v in candidates
            if v["component_type"].endswith("/ChatInput")
        )
        outgoing = next(
            v["component_type"]
            for v in metadata.search("Chat Output")["components"]
            if v["component_type"].endswith("/ChatOutput")
        )
        description = metadata.describe(outgoing)
        port = "input_value"
        assert any(
            v["name"] == port and "Message" in v["input_types"]
            for v in description["inputs"]
        )
        output = metadata.describe(incoming)["outputs"][0]["name"]
        graph, diagnostics = metadata.compile(
            DraftGraph(
                nodes=[
                    DraftNode(
                        key="input",
                        component_type=incoming,
                        fields={"input_value": "approval-original"},
                    ),
                    DraftNode(key="output", component_type=outgoing),
                ],
                edges=[
                    DraftEdge(
                        source="input", output=output, target="output", input=port
                    )
                ],
                allow_incomplete=True,
            )
        )
        flow = self.call(
            "/api/v1/flows/",
            {"name": "Approval acceptance graph " + uuid4().hex[:6], "data": graph},
        )
        models = self.call("/api/v1/laomedo/assistant/models")
        choice = next(
            (m for m in models["models"] if m["id"] == "gpt-6-luna"),
            models["models"][0],
        )
        effort = choice["efforts"][0]
        chat = self.call(
            "/api/v1/laomedo/assistant/conversations",
            {"provider": "codex", "model": choice["id"], "effort": effort},
        )
        prompt = f"Use Laomedo tools only. Inspect workflow {flow['id']}, then propose_graph_edit changing its existing Chat Input input_value from approval-original to approval-edited. Do not execute anything or create a copy. Use operation_key edit-proof. Explain that I must approve the card."
        message = self.call(
            "/api/v1/laomedo/assistant/conversations/" + chat["id"] + "/messages",
            {
                "client_message_id": str(uuid4()),
                "text": prompt,
                "model": choice["id"],
                "effort": effort,
            },
        )
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            detail = self.call("/api/v1/laomedo/assistant/conversations/" + chat["id"])
            if detail.get("actions"):
                action = detail["actions"][0]
                break
            terminal = next(
                (
                    m
                    for m in detail["messages"]
                    if m["id"] == message["id"]
                    and m["state"] in ("failed", "completed", "interrupted")
                ),
                None,
            )
            if terminal:
                raise RuntimeError("No proposal: " + str(terminal.get("error_code")))
            time.sleep(1)
        else:
            raise TimeoutError("proposal")
        before = self.call("/api/v1/flows/" + flow["id"])
        assert before["data"] == flow["data"], "Graph changed before approval"
        META.update(conversation=chat["id"], flow=flow["id"], action=action["id"])
        (ROOT / ".tools/assistant-291-live.json").write_text(json.dumps(META))
        print(
            json.dumps(
                {
                    "stage": "proposal",
                    "inertBeforeApproval": True,
                    "kind": action["kind"],
                    "conversation": chat["id"],
                }
            ),
            flush=True,
        )
        # Stop here so the real pending card can be captured before approval.


if __name__ == "__main__":
    Acceptance().run()
