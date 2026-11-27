"""Pinned local Skills give workers references, not source or editing authority."""

from copy import deepcopy
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock
from uuid import uuid4

from laomedo.agents.connections.controllers import ProviderControllers
from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.connections.models import ConnectionRecord
from laomedo.agents.connections.models import GraphNodePolicy
from laomedo.agents.connections.service import ProviderConnections
from laomedo.integrations.langflow.assistant.catalog import ComponentCatalog
from laomedo.integrations.langflow.assistant.models import (
    DraftGraph,
    ResolvedConfiguration,
    ResourceBinding,
)
from laomedo.integrations.langflow.execution.providers.admission import (
    ProviderGraphAdmission,
)
from laomedo.integrations.langflow.execution.providers.catalog import (
    ProviderComponentCatalog,
)
from laomedo.integrations.langflow.graph_admission.catalog import GitHubGraphCatalog
from laomedo.skills.registry.store import SkillStore


class PinnedSkillAdmissionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.service = ProviderConnections(self.root / "accounts")
        self.addCleanup(self.service.close)
        self.owner, self.flow, self.job = uuid4(), uuid4(), uuid4()
        self.account = ConnectionRecord(
            provider="codex",
            connection_id=uuid4(),
            credential_id=uuid4(),
            client_id="fixture",
            subject_hash="fixture",
            generation=1,
            label="Fixture",
        )
        self.service._save(self.owner, [self.account])
        source = self.root / "source"
        source.mkdir()
        (source / "SKILL.md").write_bytes(
            b"---\nname: pinned\n---\nPRIVATE_SKILL_CONTENT_NOT_FOR_GRAPH_WORKER\n"
        )
        self.store = SkillStore(self.root / "registry")
        self.reference = self.store.import_skill("pinned", source)
        self.code = "raise AssertionError('admission cannot execute operator source')"
        catalog = GitHubGraphCatalog.capture(
            {
                "fixture": {
                    kind: {"template": {"code": {"value": self.code}}}
                    for kind in (
                        "LaomedoCodexAgent",
                        "LaomedoClaudeAgent",
                        "LaomedoSkill",
                        "TextInput",
                    )
                }
            }
        )
        self.admission = ProviderGraphAdmission(
            self.service, catalog, skill_store=self.store.root
        )
        self.graph = {
            "nodes": [
                self.node(
                    "skill",
                    "LaomedoSkill",
                    {
                        "skill_id": "pinned",
                        "revision_id": self.reference["revision_id"],
                        "source": "",
                        "github_connection": "",
                        "operation": None,
                        "edit_request": "",
                    },
                ),
                self.node(
                    "agent",
                    "LaomedoCodexAgent",
                    {
                        "provider_connection": str(self.account.connection_id),
                        "operation": "fresh",
                        "model": "model",
                        "effort": "low",
                        "task": "Read the pinned Skill",
                    },
                ),
            ],
            "edges": [self.edge("skill", "agent", "skill", "skill_reference")],
        }

    def node(self, identifier, kind, values):
        return {
            "id": identifier,
            "data": {
                "id": identifier,
                "type": kind,
                "node": {
                    "template": {
                        key: {"value": value}
                        for key, value in {"code": self.code, **values}.items()
                    }
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

    def body(self):
        return {
            "request_id": str(uuid4()),
            "model": "model",
            "effort": "low",
            "task": "Read the pinned Skill",
            "skill_ref": {
                key: self.reference[key]
                for key in ("skill_id", "revision_id", "tree_hash")
            },
        }

    def test_host_pins_reference_without_skill_bytes_paths_or_accounts_in_worker(self):
        prepared = self.prepare()
        policy = prepared.plan.nodes[0].policy
        self.assertEqual(
            policy.skills[0].to_reference_payload(), self.body()["skill_ref"]
        )
        wire = prepared.job.model_dump_json()
        for private in (
            "PRIVATE_SKILL_CONTENT",
            str(self.store.root),
            str(self.account.connection_id),
        ):
            self.assertNotIn(private, wire)
        body = self.body()
        self.assertEqual(
            policy.native_request(body, "host-owned"),
            {**body, "request_id": "host-owned"},
        )
        listed = {key: value for key, value in body.items() if key != "skill_ref"}
        listed["skill_refs"] = [body["skill_ref"]]
        self.assertEqual(
            policy.native_request(listed, "host-owned")["skill_refs"],
            [body["skill_ref"]],
        )

    def test_worker_forgery_is_refused_before_native_startup(self):
        prepared = self.prepare()
        factory = Mock(side_effect=AssertionError("forgery cannot start a runner"))
        controllers = ProviderControllers(
            self.service,
            self.root / "runs",
            self.store.root,
            self.root / "source",
            factory=factory,
        )
        self.addCleanup(controllers.close)
        capability = controllers.graph_runs.admit(prepared.plan)
        body = self.body()
        listed = {key: value for key, value in body.items() if key != "skill_ref"}
        for forged in (
            {
                **body,
                "skill_ref": {
                    **body["skill_ref"],
                    "revision_id": "sha256:" + "0" * 64,
                },
            },
            body | {"skill_refs": [body["skill_ref"]]},
            {
                **listed,
                "skill_refs": [body["skill_ref"], body["skill_ref"]],
            },
        ):
            with (
                self.subTest(forged=forged),
                self.assertRaises(ProviderConnectionError),
            ):
                controllers.start_graph_node(
                    capability,
                    prepared.plan.graph_digest,
                    "agent",
                    forged,
                )
        factory.assert_not_called()

    def test_installed_authoring_compiler_preserves_the_pinned_skill_edge(self):
        installed = ProviderComponentCatalog(
            Path(__file__).resolve().parents[4] / "components"
        )
        catalog = ComponentCatalog(installed._registry)
        nodes = []
        for key, kind, fields, resources in (
            (
                "skill",
                "LaomedoSkill",
                {
                    "skill_id": "pinned",
                    "revision_id": self.reference["revision_id"],
                },
                [
                    ResourceBinding(
                        kind="skill",
                        id="pinned",
                        version=self.reference["revision_id"],
                    )
                ],
            ),
            (
                "agent",
                "LaomedoCodexAgent",
                {
                    "provider_connection": str(self.account.connection_id),
                    "model": "model",
                    "effort": "low",
                },
                [],
            ),
        ):
            identity = "laomedo/" + kind
            resolution = ResolvedConfiguration(
                owner_id=self.owner,
                conversation_id=uuid4(),
                session_key="fixture",
                component_type=identity,
                schema_revision=catalog.schema_revision(identity),
                fields=fields,
                expires_at=time.time() + 60,
                resources=resources,
                connection_id=self.account.connection_id if key == "agent" else None,
                connection_generation=1 if key == "agent" else None,
            )
            catalog.allow_resolution(resolution)
            nodes.append(
                {
                    "key": key,
                    "component_type": identity,
                    "resolution_id": resolution.id,
                    "fields": fields
                    | (
                        {"task": "Read the Skill", "operation": "fresh"}
                        if key == "agent"
                        else {}
                    ),
                }
            )
        graph, _ = catalog.compile(
            DraftGraph.model_validate(
                {
                    "nodes": nodes,
                    "edges": [
                        {
                            "source": "skill",
                            "output": "skill",
                            "target": "agent",
                            "input": "skill_reference",
                        }
                    ],
                }
            )
        )
        prepared = ProviderGraphAdmission(
            self.service, installed.admission, skill_store=self.store.root
        ).prepare(self.owner, "lease", self.flow, self.job, graph)
        self.assertEqual(
            prepared.plan.nodes[0].policy.skills[0].to_reference_payload(),
            self.body()["skill_ref"],
        )

    def test_resource_binding_must_name_the_exact_local_revision(self):
        graph = deepcopy(self.graph)
        binding = {
            "kind": "skill",
            "id": "pinned",
            "version": self.reference["revision_id"],
        }
        graph["nodes"][0]["data"]["laomedo_authoring_bindings"] = {
            "resources": [binding]
        }
        self.prepare(graph)
        for changed in (
            {**binding, "id": "foreign"},
            {**binding, "version": "sha256:" + "0" * 64},
            {**binding, "kind": "mcp"},
        ):
            with self.subTest(binding=changed):
                graph["nodes"][0]["data"]["laomedo_authoring_bindings"] = {
                    "resources": [changed]
                }
                with self.assertRaises(ProviderConnectionError):
                    self.prepare(graph)

    def test_missing_revision_blocks_admission_and_output_release(self):
        self.prepare()
        self.store._revision_dir("pinned", self.reference["revision_id"]).rename(
            self.root / "removed-revision"
        )
        with self.assertRaisesRegex(
            ProviderConnectionError, "skill_revision_unavailable"
        ):
            self.prepare()
        with self.assertRaisesRegex(
            ProviderConnectionError, "skill_revision_unavailable"
        ):
            self.admission.check_resources(self.graph)

    def test_source_private_and_mutation_fields_are_refused(self):
        for field, value in (
            ("source", "https://github.com/example/repository"),
            ("source", "/private/source"),
            ("github_connection", str(uuid4())),
            ("operation", {"action": "modify"}),
            ("edit_request", "change"),
            ("commit_id", "unapproved"),
        ):
            with self.subTest(field=field, value=value):
                graph = deepcopy(self.graph)
                graph["nodes"][0]["data"]["node"]["template"][field] = {"value": value}
                with self.assertRaises(ProviderConnectionError):
                    self.prepare(graph)

    def test_task_output_feedback_and_skill_on_verified_review_are_refused(self):
        graph = deepcopy(self.graph)
        graph["edges"][0] = self.edge("skill", "agent", "task", "task")
        with self.assertRaises(ProviderConnectionError):
            self.prepare(graph)
        graph = deepcopy(self.graph)
        graph["edges"].append(self.edge("agent", "skill", "answer", "operation"))
        with self.assertRaises(ProviderConnectionError):
            self.prepare(graph)
        graph = deepcopy(self.graph)
        account = self.account.model_copy(
            update={"provider": "claude", "connection_id": uuid4()}
        )
        self.service._save(self.owner, [self.account, account])
        graph["nodes"].append(
            self.node(
                "review",
                "LaomedoClaudeAgent",
                {
                    "provider_connection": str(account.connection_id),
                    "operation": "fresh",
                    "model": "model",
                    "effort": "low",
                    "task": "Review",
                },
            )
        )
        graph["edges"].extend(
            [
                self.edge("agent", "review", "run", "verified_changes"),
                self.edge("skill", "review", "skill", "skill_reference"),
            ]
        )
        with self.assertRaises(ProviderConnectionError):
            self.prepare(graph)

    def test_tampering_blocks_admission_and_late_output_release(self):
        self.prepare()
        self.admission.check_resources(self.graph)
        bundle = (
            self.store._revision_dir("pinned", self.reference["revision_id"])
            / "bundle/SKILL.md"
        )
        bundle.write_bytes(b"changed")
        with self.assertRaisesRegex(
            ProviderConnectionError, "skill_revision_unavailable"
        ):
            self.prepare()
        with self.assertRaisesRegex(
            ProviderConnectionError, "skill_revision_unavailable"
        ):
            self.admission.check_resources(self.graph)

    def test_shared_reference_only_graph_needs_no_account_authority(self):
        owner = uuid4()
        self.service._save(owner, [])
        prepared = self.prepare(
            {"nodes": [self.graph["nodes"][0]], "edges": []}, owner=owner
        )
        self.assertEqual(prepared.plan.nodes, ())
        self.assertEqual(prepared.job.providers, ())

    def test_non_skill_request_keeps_its_existing_semantic_shape(self):
        body = self.body()
        body.pop("skill_ref")
        body["skill_refs"] = []
        policy = GraphNodePolicy(model="model", effort="low", task=body["task"])
        self.assertEqual(
            policy.native_request(body, "host-owned"),
            body | {"request_id": "host-owned"},
        )
