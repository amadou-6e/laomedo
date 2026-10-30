"""Internal architecture and record-binding regressions; no real provider acceptance."""

import ast
import inspect
from pathlib import Path
import unittest
from unittest.mock import patch

from laomedo.agents.agents.base.agent import BaseAgent
from laomedo.agents.agents.codex.agent import CodexAgent
from laomedo.agents.agents.claude.agent import ClaudeAgent
from laomedo.agents.agents.opencode.agent import OpenCodeAgent
from laomedo.agents.errors import RunnerError
from laomedo.agents.agents.codex import settings as codex_settings
import test_local_runner
import test_claude_runner
import test_opencode_runner

ROOT = Path(__file__).resolve().parents[1]


class ProviderBoundaryTests(unittest.TestCase):
    def test_shared_runtime_never_imports_concrete_provider_or_credentials(self):
        for path in (ROOT / "src/laomedo/agents/agents/base").glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                names = (
                    [item.name for item in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                )
                for name in names:
                    self.assertFalse(
                        name.startswith(
                            tuple(
                                "laomedo.agents.agents." + provider + "."
                                for provider in ("codex", "claude", "opencode")
                            )
                            + ("laomedo.host.credentials.",)
                        ),
                        (path.name, node.lineno, name),
                    )
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.assertNotIn(
                        node.value,
                        {"codex", "claude", "opencode"},
                        (path.name, node.lineno),
                    )

    def test_providers_extend_only_the_neutral_lifecycle(self):
        for cls in (CodexAgent, ClaudeAgent, OpenCodeAgent):
            self.assertEqual(cls.__bases__, (BaseAgent,))
            self.assertFalse(cls.__abstractmethods__)
        forbidden = {
            "transport",
            "check_docker",
            "supervise_containers",
            "split_executor",
            "split_provider_config",
            "split_access_token",
            "auth_store",
            "image_id",
        }
        self.assertFalse(forbidden & set(inspect.signature(BaseAgent).parameters))
        self.assertFalse(forbidden & set(inspect.signature(OpenCodeAgent).parameters))

    def test_concrete_providers_never_import_a_sibling_provider(self):
        for path in (ROOT / "src/laomedo/agents/agents").rglob("*.py"):
            owner = path.relative_to(ROOT / "src/laomedo/agents/agents").parts[0]
            for node in ast.walk(ast.parse(path.read_text())):
                names = (
                    [item.name for item in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                )
                for name in names:
                    if (
                        name.startswith("laomedo.agents.agents.")
                        and name.split(".")[3] != "base"
                    ):
                        self.assertEqual(
                            name.split(".")[3], owner, (path.name, node.lineno, name)
                        )

    def test_graph_adapters_do_not_inherit_each_other(self):
        for provider in ("codex", "claude", "opencode"):
            path = ROOT / f"components/laomedo/{provider}_agent.py"
            tree = ast.parse(path.read_text())
            imports = [
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            ]
            self.assertIn("laomedo.integrations.langflow.agent.component", imports)
            self.assertNotIn("laomedo.codex_agent", imports)
        shared = ROOT / "src/laomedo/agents/interface/langflow/component.py"
        for node in ast.walk(ast.parse(shared.read_text())):
            if isinstance(node, ast.Attribute):
                self.assertFalse(
                    isinstance(node.value, ast.Name)
                    and node.value.id == "self"
                    and node.attr == "name"
                )

    def fixture(self, cls):
        control = cls()
        control.setUp()
        self.addCleanup(control.doCleanups)
        self.addCleanup(control.tearDown)
        return control

    def assert_record(self, control, request, expected):
        record = control.runner._prepare(request)
        self.assertEqual({key: record[key] for key in expected}, expected)
        self.assertEqual(record, control.runner.status(record["run_id"]))
        # Full schema guard: provider-specific additions are intentional, not inherited pins.
        keys = {
            "schema_version",
            "run_id",
            "status",
            "error_category",
            "source_hash",
            "workspace_mode",
            "git_baseline",
            "post_run_hash_scope",
            "effective_hash",
            "post_run_hash",
            "input_hash",
            "skill",
            "skills",
            "skill_git_exclusion",
            "provider",
            "handoff",
            "imported_artifacts",
            "requested_model",
            "requested_effort",
            "effective_model",
            "effective_effort",
            "profile",
            "execution_mode",
            "image",
            "image_id",
            "cli_version",
            "config_sha256",
            "thread_id",
            "credential",
            "runner_instance_id",
            "turns",
            "answer",
            "output_ref",
            "raw_event_ref",
            "client_request_id",
            "activity_initial_attempt_id",
            "output_requirements",
            "requirements_revision",
            "output_retries",
            "precheck",
            "request_hash",
            "cancel_requested",
            "cancel_confirmed",
        }
        if control.runner.provider == "claude":
            keys |= {
                "runtime_version",
                "turn_timeout",
                "resolved_model",
                "permission_grant",
                "native_tools",
            }
        self.assertEqual(set(record), keys)
        return record

    def test_codex_prepared_record_preserves_binding(self):
        control = self.fixture(test_local_runner.LocalRunnerTests)
        self.assert_record(
            control,
            control.request(),
            {
                "provider": "codex",
                "profile": codex_settings.VOLUME,
                "image": codex_settings.IMAGE,
                "image_id": codex_settings.IMAGE_ID,
                "execution_mode": "codex_acp",
                "cli_version": codex_settings.CLI_VERSION,
                "config_sha256": codex_settings.CONFIG_SHA256,
                "credential": None,
            },
        )

    def test_claude_prepared_record_never_contains_codex_binding(self):
        control = self.fixture(test_claude_runner.ClaudeRunnerTests)
        self.assert_record(
            control,
            control.payload,
            {
                "provider": "claude",
                "profile": control.runner.profile,
                "image": control.runner.image,
                "image_id": control.runner.image_id,
                "execution_mode": "claude_container",
                "cli_version": "Claude Code " + test_claude_runner.CLI_VERSION,
                "credential": None,
            },
        )

    def test_opencode_prepared_record_never_contains_codex_binding(self):
        control = self.fixture(test_opencode_runner.OpenCodeTests)
        self.assert_record(
            control,
            control.payload,
            {
                "provider": "opencode",
                "profile": None,
                "image": None,
                "image_id": None,
                "execution_mode": "opencode_acp",
                "cli_version": "opencode 1.18.33",
                "config_sha256": None,
                "credential": None,
            },
        )

    def test_unsupported_mediation_is_rejected_before_workspace_or_authority(self):
        for cls in (
            test_claude_runner.ClaudeRunnerTests,
            test_opencode_runner.OpenCodeTests,
        ):
            control = self.fixture(cls)
            with patch.object(control.runner, "github_authority") as authority:
                with self.assertRaisesRegex(RunnerError, "mediated_lease_required"):
                    control.runner._prepare(
                        {**control.payload, "github_authorization_ref": "untrusted"}
                    )
                authority.bind_run.assert_not_called()
                self.assertEqual(list((control.runner.state / "runs").iterdir()), [])

    def test_provider_restart_reconciles_only_the_persisted_identity(self):
        from laomedo.agents.agents.base.utils import _json

        for fixture_type in (
            test_local_runner.LocalRunnerTests,
            test_claude_runner.ClaudeRunnerTests,
        ):
            control = self.fixture(fixture_type)
            request = (
                control.request()
                if fixture_type is test_local_runner.LocalRunnerTests
                else control.payload
            )
            record = control.runner._prepare(request)
            owner = {
                "supervised": True,
                "name": "laomedo-exact-unit",
                "launch_token": "unit-capability",
            }
            record.update(status="running", container_ownership=owner)
            _json(control.runner._run_dir(record["run_id"]) / "record.json", record)
            cleanup_owner = (
                "laomedo.agents.agents.codex.agent"
                if fixture_type is test_local_runner.LocalRunnerTests
                else "laomedo.agents.agents.claude.agent"
            )
            with patch(
                cleanup_owner + ".cleanup_exact",
                return_value=(False, "identity mismatch"),
            ) as cleanup:
                if fixture_type is test_local_runner.LocalRunnerTests:
                    restarted = CodexAgent(
                        control.runner.state,
                        control.runner.store.root,
                        control.source,
                        check_docker=False,
                    )
                else:
                    restarted = ClaudeAgent(
                        control.runner.state,
                        control.runner.store.root,
                        control.source,
                        container=control.runner.container,
                    )
            identity = cleanup.call_args.args[0]
            self.assertEqual(
                (identity.name, identity.run_id, identity.token.get_secret_value()),
                (owner["name"], record["run_id"], owner["launch_token"]),
            )
            result = restarted.status(record["run_id"])
            self.assertEqual(result["status"], "interrupted")
            self.assertEqual(result["error_category"], "container_cleanup_unverified")
            self.assertFalse(result["container_ownership"]["cleanup_verified"])

    def test_opencode_restart_reads_historical_metadata_without_codex_cleanup(self):
        from laomedo.agents.agents.base.utils import _json

        control = self.fixture(test_opencode_runner.OpenCodeTests)
        record = control.runner._prepare(control.payload)
        record.update(
            status="running",
            image=codex_settings.IMAGE,
            cli_version=codex_settings.CLI_VERSION,
        )
        _json(control.runner._run_dir(record["run_id"]) / "record.json", record)
        with (
            patch(
                "laomedo.agents.agents.codex.agent.cleanup_exact",
                side_effect=AssertionError("no Codex controller"),
            ),
            patch(
                "laomedo.agents.agents.claude.agent.cleanup_exact",
                side_effect=AssertionError("no Claude controller"),
            ),
        ):
            restarted = OpenCodeAgent(
                control.runner.state, control.runner.store.root, control.source
            )
        historical = restarted.status(record["run_id"])
        self.assertEqual(historical["image"], codex_settings.IMAGE)
        self.assertEqual(historical["cli_version"], codex_settings.CLI_VERSION)
        self.assertEqual(historical["error_category"], "runner_restarted")

    def test_claude_and_opencode_do_not_validate_codex_policy(self):
        control = self.fixture(test_local_runner.LocalRunnerTests)
        from types import SimpleNamespace

        with patch.object(codex_settings, "CONFIG", ROOT / "not-a-codex-policy"):
            claude = ClaudeAgent(
                control.runner.state.parent
                / (control.runner.state.name + "-neutral-claude"),
                control.runner.store.root,
                control.source,
                container=SimpleNamespace(
                    profile="local-unit", image_id="sha256:" + "b" * 64
                ),
            )
            opencode = OpenCodeAgent(
                control.runner.state.parent
                / (control.runner.state.name + "-neutral-opencode"),
                control.runner.store.root,
                control.source,
            )
        import shutil

        for runner in (claude, opencode):
            self.addCleanup(shutil.rmtree, runner.state, ignore_errors=True)
