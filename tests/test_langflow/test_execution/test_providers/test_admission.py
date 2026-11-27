"""Pure-data plan admission; synthetic source is deliberately never executable."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from laomedo.agents.connections.models import ConnectionRecord
from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.connections.service import ProviderConnections
from laomedo.github.node_runs.errors import GitHubNodeAuthorizationError
from laomedo.integrations.langflow.graph_admission.catalog import GitHubGraphCatalog
from laomedo.integrations.langflow.execution.providers.admission import (
    ProviderGraphAdmission,
)


class ProviderAdmissionTests(unittest.TestCase):
    """Only effective pinned graph selections become native run authority."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.service = ProviderConnections(Path(directory.name))
        self.addCleanup(self.service.close)
        self.owner, self.flow, self.job = uuid4(), uuid4(), uuid4()
        self.records = tuple(
            ConnectionRecord(
                provider=provider,
                connection_id=uuid4(),
                credential_id=uuid4(),
                client_id="fixture",
                subject_hash=provider,
                generation=1,
                label="Fixture",
            )
            for provider in ("codex", "claude")
        )
        self.service._save(self.owner, list(self.records))
        self.source = (
            "raise AssertionError('admission must not execute component source')"
        )
        kinds = ("LaomedoCodexAgent", "LaomedoClaudeAgent", "LaomedoGitHubIssue")
        catalog = GitHubGraphCatalog.capture(
            {
                "fixture": {
                    kind: {"template": {"code": {"value": self.source}}}
                    for kind in kinds
                }
            }
        )
        self.admission = ProviderGraphAdmission(self.service, catalog)
        self.graph = {
            "nodes": [
                self.node("codex", kinds[0], self.records[0]),
                self.node("claude", kinds[1], self.records[1]),
            ],
            "edges": [self.edge("codex", "claude", "run", "verified_changes")],
        }

    def node(self, identifier, kind, record):
        values = {
            "code": self.source,
            "model": "model",
            "effort": "low",
            "task": "Approved task",
            "operation": "fresh",
            "provider_connection": str(record.connection_id),
        }
        return {
            "id": identifier,
            "data": {
                "id": identifier,
                "type": kind,
                "node": {
                    "template": {
                        name: {"value": value} for name, value in values.items()
                    }
                },
                "laomedo_authoring_bindings": {
                    "connection_id": str(record.connection_id),
                    "generation": 1,
                },
            },
        }

    def edge(self, source, target, output, field):
        return {
            "source": source,
            "target": target,
            "data": {
                "sourceHandle": {"name": output},
                "targetHandle": {"fieldName": field},
            },
        }

    def prepare(self, graph=None, owner=None):
        return self.admission.prepare(
            owner or self.owner, "lease", self.flow, self.job, graph or self.graph
        )

    def test_host_plan_derives_review_edge_and_strips_worker_account_metadata(self):
        prepared = self.prepare()
        self.assertEqual(prepared.plan.nodes[1].review_source, "codex")
        self.assertEqual(
            prepared.plan.nodes[0].connection_id, self.records[0].connection_id
        )
        serialized = prepared.job.model_dump_json()
        for record in self.records:
            self.assertNotIn(str(record.connection_id), serialized)
        self.assertNotIn("laomedo_authoring_bindings", serialized)
        self.assertEqual(
            prepared.plan.graph_digest, "sha256:" + prepared.job.graph_digest
        )
        self.assertEqual(
            self.graph["nodes"][0]["data"]["node"]["template"]["provider_connection"][
                "value"
            ],
            str(self.records[0].connection_id),
        )

    def test_foreign_owner_stale_epoch_and_unsupported_authority_refuse(self):
        with self.assertRaises(ProviderConnectionError):
            self.prepare(owner=uuid4())
        graph = deepcopy(self.graph)
        graph["nodes"][0]["data"]["laomedo_authoring_bindings"]["generation"] = 2
        with self.assertRaises(ProviderConnectionError):
            self.prepare(graph)
        for field, value in (
            ("operation", "resume"),
            ("skill_reference", [{}]),
            ("mcp_tools", [{}]),
            ("verified_changes", {"run_id": str(uuid4())}),
        ):
            with self.subTest(field=field):
                graph = deepcopy(self.graph)
                graph["nodes"][0]["data"]["node"]["template"][field] = {"value": value}
                with self.assertRaises(ProviderConnectionError):
                    self.prepare(graph)

    def test_wrong_review_output_dynamic_selection_or_edited_source_refuse(self):
        for output, field in (
            ("answer", "verified_changes"),
            ("run", "provider_connection"),
            ("run", "model"),
        ):
            graph = deepcopy(self.graph)
            graph["edges"] = [self.edge("codex", "claude", output, field)]
            with self.subTest(field=field), self.assertRaises(ProviderConnectionError):
                self.prepare(graph)
        graph = deepcopy(self.graph)
        graph["nodes"][0]["data"]["node"]["template"]["code"]["value"] += "\n# edited"
        with self.assertRaises(GitHubNodeAuthorizationError):
            self.prepare(graph)

    def test_public_issue_is_exact_anonymous_read_not_a_dynamic_operation(self):
        graph = deepcopy(self.graph)
        issue = self.node("issue", "LaomedoGitHubIssue", self.records[0])
        issue["data"]["node"]["template"] = {
            name: {"value": value}
            for name, value in {
                "code": self.source,
                "repository_url": "https://github.com/owner/repo",
                "issue_choice": "#12 Selected issue",
                "public_service_only": True,
            }.items()
        }
        graph["nodes"].append(issue)
        graph["edges"].append(self.edge("issue", "codex", "task", "task"))
        prepared = self.prepare(graph)
        self.assertEqual(prepared.issues[0].number, 12)
        self.assertTrue(prepared.plan.nodes[0].policy.task_from_input)
        issue["data"]["node"]["template"]["public_service_only"]["value"] = False
        with self.assertRaises(ProviderConnectionError):
            self.prepare(graph)

    def test_duplicate_input_and_cycles_refuse_before_native_construction(self):
        graph = deepcopy(self.graph)
        graph["edges"].append(self.edge("codex", "claude", "run", "verified_changes"))
        with self.assertRaises(ProviderConnectionError):
            self.prepare(graph)
        graph = deepcopy(self.graph)
        graph["edges"].append(self.edge("claude", "codex", "answer", "task"))
        with self.assertRaises(ProviderConnectionError):
            self.prepare(graph)
