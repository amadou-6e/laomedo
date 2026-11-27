"""Use real installed classes to verify startup-only metadata for the isolated mode."""

from pathlib import Path
import asyncio
from importlib.util import module_from_spec, spec_from_file_location
import threading
import time
import sys
from types import SimpleNamespace
from uuid import UUID, uuid4
import unittest
from unittest.mock import patch
from laomedo.agents.connections.models import ConnectionRecord
from laomedo.integrations.langflow.assistant.catalog import ComponentCatalog
from laomedo.integrations.langflow.assistant.models import (
    DraftGraph,
    ResolvedConfiguration,
)
from laomedo.integrations.langflow.execution.providers.admission import (
    ProviderGraphAdmission,
)

from laomedo.integrations.langflow.execution.providers.catalog import (
    ProviderComponentCatalog,
)


class ProviderCatalogTests(unittest.TestCase):
    """Fixed installed metadata supplies both authoring and native source pins."""

    def test_skill_import_metadata_and_reference_output_do_not_access_services(self):
        from laomedo.skills.interface.sources.settings import Settings as SourceSettings
        from laomedo.skills.interface.operations.settings import (
            Settings as OperationSettings,
        )

        root = Path(__file__).resolve().parents[4]
        original = Path.read_text
        # Windows initializes its event-loop wakeup socket before the I/O guard.
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        def read(path, *args, **kwargs):
            if path.name in {
                "api-token",
                "auth.json",
                ".credentials.json",
                ".env",
                "secret_key",
            }:
                raise AssertionError("metadata cannot read credentials")
            return original(path, *args, **kwargs)

        with (
            patch(
                "socket.socket.connect",
                side_effect=AssertionError("metadata cannot connect"),
            ),
            patch(
                "urllib.request.urlopen",
                side_effect=AssertionError("metadata cannot request"),
            ),
            patch(
                "threading.Thread.start",
                side_effect=AssertionError("metadata cannot start work"),
            ),
            patch.object(
                SourceSettings,
                "__init__",
                side_effect=AssertionError("metadata cannot load source credentials"),
            ),
            patch.object(
                OperationSettings,
                "__init__",
                side_effect=AssertionError(
                    "metadata cannot load operation credentials"
                ),
            ),
            patch.object(Path, "read_text", new=read),
        ):
            installed = ProviderComponentCatalog(root / "components")
            self.assertIn("LaomedoSkill", installed._registry["laomedo"])
            spec = spec_from_file_location(
                "skill_metadata_control", root / "components/laomedo/skill.py"
            )
            module = module_from_spec(spec)
            with patch.dict(sys.modules, {spec.name: module}):
                spec.loader.exec_module(module)
                skill = module.LaomedoSkill()
            skill.skill_id = "fixture"
            skill.revision_id = "sha256:" + "a" * 64
            skill._pre_run_setup()
            reference = loop.run_until_complete(skill.routed_skill_output()).data
            self.assertEqual(
                reference,
                {
                    "skill_id": "fixture",
                    "revision_id": skill.revision_id,
                    "tree_hash": skill.revision_id,
                },
            )

    def test_actual_authoring_compiler_and_planner_accept_the_connected_review_workflow(
        self,
    ):
        root = Path(__file__).resolve().parents[4]
        installed = ProviderComponentCatalog(root / "components")
        catalog = ComponentCatalog(installed._registry)
        owner = uuid4()
        records = [
            ConnectionRecord(
                provider=p,
                connection_id=uuid4(),
                credential_id=uuid4(),
                client_id="fixture",
                subject_hash=p,
                generation=1,
                label="Fixture",
            )
            for p in ("codex", "claude")
        ]
        values = [
            (
                "issue",
                "laomedo/LaomedoGitHubIssue",
                {
                    "repository_url": "https://github.com/owner/repo",
                    "labels": [],
                    "state": "open",
                    "issue_choice": "#12 Fixture",
                    "public_service_only": True,
                },
                None,
            ),
            (
                "codex",
                "laomedo/LaomedoCodexAgent",
                {
                    "provider_connection": str(records[0].connection_id),
                    "model": "fixture",
                    "effort": "low",
                },
                records[0],
            ),
            (
                "claude",
                "laomedo/LaomedoClaudeAgent",
                {
                    "provider_connection": str(records[1].connection_id),
                    "model": "fixture",
                    "effort": "low",
                },
                records[1],
            ),
        ]
        nodes = []
        for key, identity, fields, record in values:
            resolution = ResolvedConfiguration(
                owner_id=owner,
                conversation_id=uuid4(),
                session_key="fixture",
                component_type=identity,
                schema_revision=catalog.schema_revision(identity),
                fields=fields,
                expires_at=time.time() + 60,
                connection_id=record.connection_id if record else None,
                connection_generation=1 if record else None,
            )
            catalog.allow_resolution(resolution)
            static = (
                {
                    "task": "Review the actual patch.",
                    "operation": "fresh",
                    "run_timeout_seconds": 180,
                }
                if key == "claude"
                else ({"operation": "fresh"} if key == "codex" else {})
            )
            nodes.append(
                {
                    "key": key,
                    "component_type": identity,
                    "fields": fields | static,
                    "resolution_id": resolution.id,
                }
            )
        nodes.extend(
            [
                {
                    "key": "combine",
                    "component_type": "input_output/CombineText",
                    "fields": {"text1": "Make a real edit.", "delimiter": "\n"},
                },
                {
                    "key": "output",
                    "component_type": "input_output/TextOutput",
                    "fields": {},
                },
            ]
        )
        graph, _ = catalog.compile(
            DraftGraph.model_validate(
                {
                    "nodes": nodes,
                    "edges": [
                        {
                            "source": "issue",
                            "output": "task",
                            "target": "combine",
                            "input": "text2",
                        },
                        {
                            "source": "combine",
                            "output": "combined_text",
                            "target": "codex",
                            "input": "task",
                        },
                        {
                            "source": "codex",
                            "output": "run",
                            "target": "claude",
                            "input": "verified_changes",
                        },
                        {
                            "source": "claude",
                            "output": "answer",
                            "target": "output",
                            "input": "input_value",
                        },
                    ],
                }
            )
        )
        connections = SimpleNamespace(
            _lock=threading.RLock(),
            check_lease=lambda lease: None,
            admitted=lambda selected_owner, selected: next(
                r for r in records if r.connection_id == UUID(str(selected))
            ),
        )
        prepared = ProviderGraphAdmission(connections, installed.admission).prepare(
            owner, "fixture", uuid4(), uuid4(), graph
        )
        self.assertEqual(
            prepared.plan.nodes[1].review_source, "LaomedoCodexAgent-codex"
        )
        self.assertTrue(prepared.plan.nodes[0].policy.task_from_input)
        self.assertEqual(prepared.issues[0].number, 12)

    def test_fixed_catalog_contains_real_audited_component_sources_without_discovery(
        self,
    ):
        from laomedo.agents.connections.controllers import ProviderControllers

        root = Path(__file__).resolve().parents[4]
        with patch.object(
            ProviderControllers,
            "current",
            side_effect=AssertionError("startup must not discover accounts"),
        ):
            catalog = ProviderComponentCatalog(root / "components")
        classified = {
            entry.classification for entry in catalog.admission.snapshot.entries
        }
        self.assertEqual(
            {
                "LaomedoCodexAgent",
                "LaomedoClaudeAgent",
                "LaomedoOpenCodeAgent",
                "LaomedoGitHubIssue",
                "LaomedoSkill",
                "TextInput",
                "TextOutput",
                "Prompt Template",
                "CombineText",
                "MCPTools",
            },
            classified,
        )
