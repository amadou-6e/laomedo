"""One explicitly authorized native feedback task and reversible title-only check.

This exp-only harness never changes normal runner limits or service policies.
Preparation performs reads and creates a synthetic pinned instruction. Execution
requires the human-approved exact proposal; no issue/body/label writes exist.
"""

import argparse
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import threading
import time
from urllib.request import build_opener, ProxyHandler, Request
from uuid import uuid4

from laomedo.github.pull_requests.gateway import GitHubPRGateway
from laomedo.github.transport.rest.transport import GitHubRestTransport
from laomedo.github.interface.pull_requests.server import PullRequestServer
from laomedo.host.credentials.token import HostTokenConnection
from laomedo.host.http import NoRedirect
from laomedo.host.mediation.errors import KnownRejected
from laomedo.host.mediation.store import MediationStore
from laomedo.skills.registry.store import SkillStore


class TitleOnlyTransport(GitHubRestTransport):
    """Refuse every write except the approved marker and exact original title."""

    def __init__(self, proposal, credential):
        super().__init__(proposal["repository"], credential)
        self.proposal = proposal
        self.phase = "temporary_title"
        self.write_attempts = 0
        self.write_lock = threading.Lock()

    def _call(self, method, path, body, *args, **kwargs):
        if method != "GET":
            with self.write_lock:
                expected_path = f"/repos/{self.proposal['repository']}/pulls/268"
                if (
                    method != "PATCH" or path != expected_path
                    or body != {"title": self.proposal[self.phase]}
                    or self.write_attempts >= 2
                ):
                    raise KnownRejected("pr_target_denied")
                self.write_attempts += 1
        return super()._call(method, path, body, *args, **kwargs)


class PRReadinessHarness:
    repository = "amadou-6e/laomedo"
    number = 268

    def __init__(self, checkout):
        self.checkout = checkout.resolve()
        self.runtime = Path(os.environ["TEMP"]) / "laomedo-graph-20261107"
        self.campaign = Path(__file__).resolve().parent
        self.state = self.runtime / "readiness" / "pr268-live"
        self.state.mkdir(parents=True, exist_ok=True)
        self.connection = HostTokenConnection(
            connection_id="pr268-approved-title-check", generation=1,
            repository=self.repository, token_file=self.checkout.parents[2] / ".env",
            key="GH_LAOMEDO",
            forbidden_mount=self.checkout.parents[2] / "docs/vision-and-goals",
        )
        self.bindings = {}
        self.run_id = "pr268-readiness-" + uuid4().hex

    def credential(self, connection_id=None, connection_generation=None):
        return self.connection.token(
            connection_id or self.connection.connection_id,
            self.connection.generation if connection_generation is None else connection_generation,
        )

    def prepare(self):
        transport = GitHubRestTransport(self.repository, self.credential)
        pr = transport(self.repository, "pr_node_read", {"number": self.number})
        proposal = {
            "approval": "pending", "repository": self.repository, "pr": self.number,
            "original_title": pr["title"],
            "temporary_title": pr["title"] + " [QA 20261110]",
            "head_branch": pr["head"]["branch"], "base_branch": pr["base"],
            "head_sha": pr["head"]["sha"], "model_tasks": 1,
            "maximum_write_attempts": 2, "fields": ["title"],
        }
        instruction = self.campaign / "instruction"
        instruction.mkdir(exist_ok=True)
        expected = {"action": "modify", "changes": {"title": proposal["temporary_title"]}}
        (instruction / "SKILL.md").write_text(
            "---\nname: pr-feedback-readiness-268\ndescription: Return the approved title-only readiness proposal.\n---\n\n"
            "Do not use tools or edit files. Return exactly this JSON and no other text:\n\n"
            + json.dumps(expected) + "\n", encoding="utf-8",
        )
        record = SkillStore(self.runtime / "registry").import_skill(
            "pr-feedback-readiness-268", instruction
        )
        token = (self.runtime / "runner/api-token").read_text(encoding="utf-8").strip()
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open(Request(
            "http://127.0.0.1:8765/v1/models", headers={"Authorization": "Bearer " + token}
        ), timeout=30) as response:
            models = json.load(response)["models"]
        identifiers = [item.get("id") if isinstance(item, dict) else item for item in models]
        model = next(value for value in identifiers if isinstance(value, str) and value)
        spec = importlib.util.spec_from_file_location("readiness_graph", self.checkout / "examples/github/build_flow.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        flow = builder.build(
            self.repository, self.number, pr["title"], feedback=True,
            runner_url="http://127.0.0.1:8765", skill_id=record["skill_id"], revision=record["revision_id"],
        )
        flow["id"] = str(uuid4())
        flow["name"] = "PR268 title-only readiness (approval pending)"
        agent = next(node for node in flow["data"]["nodes"] if node["id"] == "agent")
        for field, value in (("model", model), ("effort", "low")):
            agent["data"]["node"]["template"][field]["value"] = value
            agent["data"]["node"]["template"][field]["options"] = [value]
        (self.campaign / "proposal.json").write_text(json.dumps(proposal, indent=2) + "\n", encoding="utf-8")
        (self.campaign / "flow.json").write_text(json.dumps(flow, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"prepared": True, "model_task_submitted": False, "writes": 0,
                          "temporary_title": proposal["temporary_title"], "flow_id": flow["id"]}))

    def resolve(self, ref):
        return self.bindings[ref]

    def issue(self, ref):
        grant_id, token = self.mediation.issue(
            run_id=self.run_id, invocation_id=ref, repository=self.repository,
            operations={"pr_node_update"}, ttl_seconds=60,
            branch=self.proposal["head_branch"], base_branch=self.proposal["base_branch"],
            target_prs={self.number: self.proposal["base_branch"]},
            connection_id=self.connection.connection_id, connection_generation=1,
            approval_identity="explicit-human-title-only-readiness-approval",
        )
        self.bindings[ref] = {"token": token, "run_id": self.run_id, "repository": self.repository}
        return grant_id

    def renew(self, grant_id, stop):
        deadline = time.monotonic() + 180
        while not stop.wait(15) and time.monotonic() < deadline:
            if not self.mediation.renew_grant(grant_id, 60):
                break

    async def execute(self, approval_path):
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        self.proposal = json.loads((self.campaign / "proposal.json").read_text(encoding="utf-8"))
        if approval.get("proposal") != self.proposal or approval.get("human_authorized") is not True:
            raise RuntimeError("Exact human scope approval is required; no task or write submitted")
        self.transport = TitleOnlyTransport(self.proposal, self.credential)
        current = self.transport(self.repository, "pr_node_read", {"number": self.number})
        if current["title"] != self.proposal["original_title"]:
            raise RuntimeError("The original title changed; re-prepare the proposal")
        self.mediation = MediationStore(self.state / "mediation.sqlite", connection_is_current=self.connection.current)
        grant_id = self.issue("qa-feedback")
        gateway = GitHubPRGateway(
            {self.repository: self.transport}, self.mediation, self.resolve,
            feedback_grants={self.repository + "#268": "qa-feedback"},
        )
        server = PullRequestServer(gateway, (self.runtime / "runner/api-token").read_text(encoding="utf-8").strip(), port=8785)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        stop = threading.Event()
        renewal = threading.Thread(target=self.renew, args=(grant_id, stop), daemon=True)
        renewal.start()
        os.environ.update(
            LAOMEDO_GITHUB_PR_URL="http://127.0.0.1:8785",
            LAOMEDO_GITHUB_PR_TOKEN_FILE=str(self.runtime / "runner/api-token"),
            LAOMEDO_RUNNER_TOKEN_FILE=str(self.runtime / "runner/api-token"),
            LAOMEDO_SKILL_STORE=str(self.runtime / "registry"),
            LAOMEDO_AGENT_ACTIVITY_DB=str(self.state / "activity.sqlite"),
        )
        try:
            from lfx.graph.graph.base import Graph
            from laomedo.integrations.langflow.agent.component import _STOP_TASKS

            flow = json.loads((self.campaign / "flow.json").read_text(encoding="utf-8"))
            graph = Graph.from_payload(
                flow, flow_id=flow["id"], user_id="pr268-scoped-readiness-owner"
            )
            graph.set_run_id()
            graph_error = None
            try:
                graph_result = await asyncio.wait_for(graph.arun(inputs=[{}], outputs=["pr"]), timeout=180)
                (self.state / "graph-result.txt").write_text(str(graph_result), encoding="utf-8")
            except Exception as error:
                graph_error = type(error).__name__
            finally:
                if _STOP_TASKS:
                    await asyncio.wait_for(asyncio.gather(*tuple(_STOP_TASKS), return_exceptions=True), timeout=30)
            remote = self.transport(self.repository, "pr_node_read", {"number": self.number})
            operation = getattr(graph.get_vertex("pr").custom_component, "_pr_execution_cache", {}).get("operation")
            print(json.dumps({"graph_operation": operation}))
            if remote["title"] != self.proposal["temporary_title"]:
                print(json.dumps({"model_task_limit": 1,
                                  "write_attempts": self.transport.write_attempts,
                                  "original_title_unchanged": remote["title"] == self.proposal["original_title"],
                                  "graph_error_type": graph_error}))
                raise RuntimeError("The title-only feedback result was not verified; no replay")
            stop.set()
            self.mediation.revoke_run(self.run_id)
            self.issue("qa-restore")
            gateway.feedback_grants.clear()
            self.transport.phase = "original_title"
            latest = gateway.execute("https://github.com/" + self.repository, [], "open", self.number)
            outcome = gateway.execute(
                "https://github.com/" + self.repository, [], "open", self.number,
                operation={"action": "modify", "request_id": "restore-" + uuid4().hex,
                           "grant_ref": "qa-restore", "changes": {"title": self.proposal["original_title"]}},
                expected=latest["content_digest"],
            )
            final = self.transport(self.repository, "pr_node_read", {"number": self.number})
            print(json.dumps({"model_tasks": 1, "write_attempts": self.transport.write_attempts,
                              "restore_status": outcome["operation"]["status"],
                              "graph_error_type": graph_error,
                              "original_title_restored": final["title"] == self.proposal["original_title"]}))
            if outcome["operation"]["status"] != "succeeded" or final["title"] != self.proposal["original_title"]:
                raise RuntimeError("Restoration remains unconfirmed; do not replay")
            if graph_error is not None:
                raise RuntimeError("Original title restored, but graph completion remains unconfirmed")
        finally:
            stop.set()
            self.mediation.revoke_run(self.run_id)
            server.shutdown()
            server.server_close()
            renewal.join(timeout=1)

    @classmethod
    def main(cls):
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--checkout", type=Path, required=True)
        parser.add_argument("--approval-file", type=Path)
        args = parser.parse_args()
        harness = cls(args.checkout)
        if args.approval_file is None:
            harness.prepare()
        else:
            asyncio.run(harness.execute(args.approval_file))


if __name__ == "__main__":
    PRReadinessHarness.main()
