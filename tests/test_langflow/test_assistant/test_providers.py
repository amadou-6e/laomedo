"""Exact saved-account chat composition; fixtures, not live provider acceptance."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from uuid import uuid4

from laomedo.agents.connections.models import ConnectionRecord
from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.connections.service import ProviderConnections
from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.runner import AssistantRunner
from laomedo.integrations.langflow.assistant.runtime import AssistantRuntime
from laomedo.integrations.langflow.assistant.settings import AssistantSettings


class ProviderCompositionTests(unittest.TestCase):
    """Exercise authority and delegation without Docker or model calls."""

    def test_live_session_lookup_maps_manager_refusal_without_reconstruction(self):
        owner, account, run_id = uuid4(), uuid4(), str(uuid4())
        manager = Mock()
        manager.assistant_live_session.side_effect = ProviderConnectionError(
            "provider_connection_unavailable"
        )
        runner = AssistantRunner(
            AssistantSettings(app_url="http://127.0.0.1:17881"),
            owner,
            "codex",
            account,
            1,
            controllers=manager,
        )
        with self.assertRaises(AssistantError) as refused:
            runner.has_live_session(run_id)
        self.assertEqual(refused.exception.code, "provider_connection_unavailable")
        manager.assistant_live_session.assert_called_once_with(
            owner, account, 1, run_id
        )
        manager.assistant_endpoint.assert_not_called()

    def test_account_and_epoch_are_part_of_runner_identity(self):
        owner, account, other = uuid4(), uuid4(), uuid4()
        key = AssistantRuntime._runner_key(owner, "codex", account, 1)
        self.assertNotEqual(key, AssistantRuntime._runner_key(owner, "codex", other, 1))
        self.assertNotEqual(
            key, AssistantRuntime._runner_key(owner, "codex", account, 2)
        )
        self.assertNotEqual(
            key, AssistantRuntime._runner_key(owner, "claude", account, 1)
        )

    def test_missing_binding_refuses_without_constructing_an_agent(self):
        manager = Mock()
        runner = AssistantRunner(AssistantSettings(), uuid4(), controllers=manager)
        with self.assertRaises(AssistantError):
            runner.request("GET", "/v1/models")
        manager.assistant_endpoint.assert_not_called()

    def test_saved_binding_admission_has_no_foreign_epoch_provider_or_account_fallback(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            service = ProviderConnections(Path(temporary) / "credentials")
            try:
                owner, selected = uuid4(), uuid4()
                record = ConnectionRecord(
                    connection_id=selected,
                    credential_id=uuid4(),
                    client_id="fixture",
                    subject_hash="fixture",
                    generation=1,
                    label="Saved account",
                )
                service._save(owner, [record])
                runtime = AssistantRuntime(AssistantSettings())
                runtime.provider_connections = service
                runtime.check_connection(owner, "codex", selected, 1)
                for args in (
                    (owner, "codex", None, None),
                    (uuid4(), "codex", selected, 1),
                    (owner, "codex", selected, 2),
                    (owner, "claude", selected, 1),
                ):
                    with self.subTest(args=args), self.assertRaises(AssistantError):
                        runtime.check_connection(*args)
                service._save(
                    owner, [record.model_copy(update={"lifecycle": "disconnecting"})]
                )
                with self.assertRaises(AssistantError):
                    runtime.check_connection(owner, "codex", selected, 1)
            finally:
                service.close()

    def test_http_adapter_reads_current_gateway_token_and_leaves_shared_manager_running(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            token = Path(temporary) / "token"
            token.write_text("first", encoding="utf-8")
            manager = Mock()
            manager.assistant_endpoint.return_value = ("http://127.0.0.1:12345", token)
            owner, account = uuid4(), uuid4()
            runner = AssistantRunner(
                AssistantSettings(), owner, "codex", account, 3, controllers=manager
            )
            response = Mock()
            response.read.return_value = json.dumps({"models": []}).encode()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            runner.opener = Mock()
            runner.opener.open.return_value = response
            runner.request("GET", "/v1/models")
            self.assertEqual(
                runner.opener.open.call_args.args[0].get_header("Authorization"),
                "Bearer first",
            )
            token.write_text("second", encoding="utf-8")
            runner.request("POST", "/v1/runs/async", {"task": "/status"})
            self.assertEqual(
                runner.opener.open.call_args.args[0].get_header("Authorization"),
                "Bearer second",
            )
            manager.assistant_endpoint.assert_called_with(
                owner, account, 3, run_id=None
            )
            runner.shutdown()
            manager.close.assert_not_called()
