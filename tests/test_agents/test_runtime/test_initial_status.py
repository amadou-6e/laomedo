"""Initial native status never becomes a model prompt; fixtures, not live acceptance."""

import unittest
import time
from unittest.mock import AsyncMock, Mock, patch
from laomedo.agents.agents.base.agent import BaseAgent
from laomedo.agents.errors import RunnerError
from laomedo.host.credentials.siwc.errors import AuthError
from test_agents.test_runtime.utils import prepare_runner
from test_agents.test_runtime.commands import InitialStatusTransport
from test_agents.test_runtime.transport import FakeServer


class InitialStatusTests(unittest.TestCase):
    def setUp(self):
        prepare_runner(self)
        self.addCleanup(self.runner.close)
        FakeServer.turn_inputs.clear()

    def request(self):
        return {
            "task": "/status",
            "model": "test-model",
            "effort": "low",
            "initial_native_command": "status",
        }

    def test_idle_refresh_in_flight_survives_watcher_then_resumes(self):
        result, identity = self._authenticated_status()
        self.runner.auth.account.return_value = {"state": "refresh_in_flight"}
        before = self.runner.auth.account.call_count
        deadline = time.monotonic() + 4
        while (
            self.runner.auth.account.call_count < before + 3
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        self.assertGreaterEqual(self.runner.auth.account.call_count, before + 3)
        self.assertTrue(self.runner.has_live_session(result["run_id"]))
        self.assertEqual(FakeServer.turn_inputs, [])
        self.runner.auth.account.return_value = {"state": "active"}
        self.runner.auth.access_token.return_value = ("fixture-renewed-token", identity)
        with patch.object(
            InitialStatusTransport, "refresh_credential", new=AsyncMock(), create=True
        ) as refresh:
            following = self.runner.resume(
                result["run_id"],
                "After renewal",
                expected_thread_id=result["thread_id"],
                expected_post_run_hash=result["post_run_hash"],
                model="test-model",
                effort="low",
            )
        self.assertEqual(
            following["status"], "completed", following.get("error_category")
        )
        self.assertEqual(following["thread_id"], result["thread_id"])
        refresh.assert_awaited_once_with("fixture-renewed-token")
        self.assertEqual(FakeServer.turn_inputs, ["After renewal"])

    def test_idle_refresh_does_not_relax_active_authorization_or_identity(self):
        result, identity = self._authenticated_status()
        held = self.runner._idle_sessions[result["run_id"]]
        self.runner.auth.account.return_value = {"state": "refresh_in_flight"}
        self.assertTrue(held.runtime.authorization_probe(idle=True))
        self.assertFalse(held.runtime.authorization_probe())
        self.runner.auth.summary.return_value = {
            **identity,
            "provider_subject_hash": "different",
        }
        self.assertFalse(held.runtime.authorization_probe(idle=True))
        self.runner.auth.summary.return_value = {**identity, "generation": 2}
        self.assertFalse(held.runtime.authorization_probe(idle=True))
        self.runner.auth.summary.return_value = identity
        self.runner.auth.account.side_effect = AuthError("auth_revoked")
        self.assertFalse(held.runtime.authorization_probe(idle=True))

    def test_idle_unknown_refresh_is_closed_with_sanitized_reason(self):
        result, _ = self._authenticated_status()
        self.runner.auth.account.return_value = {"state": "refresh_unknown"}
        deadline = time.monotonic() + 3
        while (
            self.runner.has_live_session(result["run_id"])
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        self.assertFalse(self.runner.has_live_session(result["run_id"]))
        record = self.runner.status(result["run_id"])
        self.assertEqual(record["live_session_close_reason"], "auth_refresh_unknown")
        self.assertEqual(record["controller_cleanup"], "confirmed")
        self.assertEqual(FakeServer.turn_inputs, [])

    def test_idle_refresh_wait_is_bounded(self):
        result, _ = self._authenticated_status()
        held = self.runner._idle_sessions[result["run_id"]]
        self.runner.auth.account.return_value = {"state": "refresh_in_flight"}
        with patch(
            "laomedo.agents.agents.codex.agent.time.monotonic",
            side_effect=[100, 100, 131],
        ):
            self.assertTrue(held.runtime.authorization_probe(idle=True))
            self.assertFalse(held.runtime.authorization_probe(idle=True))
        self.assertEqual(
            held.runtime.authorization_failure["code"], "auth_refresh_timeout"
        )

    def test_rotated_access_token_updates_the_existing_native_session(self):
        result, identity = self._authenticated_status()
        with patch.object(
            InitialStatusTransport, "refresh_credential", new=AsyncMock(), create=True
        ) as refresh:
            self.assertTrue(self.runner.has_live_session(result["run_id"]))
            self.runner.auth.access_token.return_value = (
                "fixture-renewed-token",
                identity,
            )
            following = self.runner.resume(
                result["run_id"],
                "Use the refreshed credential",
                expected_thread_id=result["thread_id"],
                expected_post_run_hash=result["post_run_hash"],
                model="test-model",
                effort="low",
            )
        self.assertEqual(
            following["status"], "completed", following.get("error_category")
        )
        self.assertEqual(following["thread_id"], result["thread_id"])
        refresh.assert_awaited_once_with("fixture-renewed-token")
        self.assertEqual(FakeServer.turn_inputs, ["Use the refreshed credential"])
        self.assertFalse(self.runner.has_live_session(result["run_id"]))

    def test_control_only_start_retains_resumable_thread_without_a_model_turn(self):
        self.runner.transport = InitialStatusTransport
        result = self.runner.start(self.request())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["turns"], [])
        self.assertTrue(self.runner.has_live_session(result["run_id"]))
        self.assertEqual(result["controller_cleanup"], "retained")
        self.assertEqual(FakeServer.turn_inputs, [])
        self.assertEqual(result["thread_id"], "native-thread")
        self.assertTrue(result["post_run_hash"])
        self.assertEqual(len(result["native_command_receipts"]), 1)
        following = self.runner.resume(
            result["run_id"],
            "Hello",
            expected_thread_id=result["thread_id"],
            expected_post_run_hash=result["post_run_hash"],
            model="test-model",
            effort="low",
        )
        self.assertEqual(following["status"], "completed")
        self.assertEqual(following["thread_id"], result["thread_id"])
        self.assertEqual(FakeServer.turn_inputs, ["Hello"])
        self.assertFalse(self.runner.has_live_session(result["run_id"]))
        self.assertEqual(following["controller_cleanup"], "confirmed")

    def test_unconfirmed_credential_update_closes_without_a_model_prompt(self):
        result, identity = self._authenticated_status()
        held = self.runner._idle_sessions[result["run_id"]]
        self.runner.auth.access_token.return_value = ("fixture-renewed-token", identity)
        with patch.object(
            InitialStatusTransport,
            "refresh_credential",
            new=AsyncMock(
                side_effect=RunnerError("codex_credential_update_unconfirmed")
            ),
            create=True,
        ) as refresh:
            following = self.runner.resume(
                result["run_id"],
                "Must not dispatch",
                expected_thread_id=result["thread_id"],
                expected_post_run_hash=result["post_run_hash"],
                model="test-model",
                effort="low",
            )
        refresh.assert_awaited_once()
        self.assertEqual(following["status"], "failed")
        self.assertEqual(
            following["error_category"], "codex_credential_update_unconfirmed"
        )
        self.assertTrue(held.runtime.log.closed)
        self.assertEqual(following["controller_cleanup"], "confirmed")
        self.assertFalse(self.runner.has_live_session(result["run_id"]))
        self.assertEqual(FakeServer.turn_inputs, [])

    def test_changed_account_refuses_before_native_credential_update(self):
        result, identity = self._authenticated_status()
        self.runner.auth.access_token.return_value = (
            "fixture-other-account-token",
            {**identity, "credential_ref": "other-account"},
        )
        with patch.object(
            InitialStatusTransport, "refresh_credential", new=AsyncMock(), create=True
        ) as refresh:
            with self.assertRaisesRegex(RunnerError, "resume_auth_identity_mismatch"):
                self.runner.resume(
                    result["run_id"],
                    "Must not dispatch",
                    expected_thread_id=result["thread_id"],
                    expected_post_run_hash=result["post_run_hash"],
                    model="test-model",
                    effort="low",
                )
        refresh.assert_not_awaited()
        self.assertEqual(FakeServer.turn_inputs, [])

    def test_idle_cancellation_releases_the_controller_without_dispatching_a_turn(self):
        self.runner.transport = InitialStatusTransport
        result = self.runner.start(self.request())
        held = self.runner._idle_sessions[result["run_id"]]
        cancelled = self.runner.cancel(result["run_id"])
        self.assertFalse(self.runner.has_live_session(result["run_id"]))
        self.assertTrue(held.runtime.log.closed)
        self.assertEqual(cancelled["live_session"], "closed")
        self.assertEqual(cancelled["controller_cleanup"], "confirmed")
        self.assertEqual(FakeServer.turn_inputs, [])
        refused = self.runner.resume(
            result["run_id"],
            "Do not replay",
            expected_thread_id=result["thread_id"],
            expected_post_run_hash=result["post_run_hash"],
            model="test-model",
            effort="low",
        )
        self.assertEqual(refused["status"], "failed")
        self.assertEqual(refused["error_category"], "codex_idle_session_unavailable")
        self.assertEqual(FakeServer.turn_inputs, [])

    def test_idle_expiry_closes_resources_and_preserves_completed_status_receipt(self):
        self.runner.transport = InitialStatusTransport
        with patch.dict("os.environ", {"LAOMEDO_CODEX_IDLE_SESSION_SECONDS": "0.01"}):
            result = self.runner.start(self.request())
        deadline = time.monotonic() + 3
        while (
            self.runner.has_live_session(result["run_id"])
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        self.assertFalse(self.runner.has_live_session(result["run_id"]))
        record = self.runner.status(result["run_id"])
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["live_session"], "closed")
        self.assertEqual(record["controller_cleanup"], "confirmed")
        self.assertEqual(len(record["native_command_receipts"]), 1)
        self.assertEqual(FakeServer.turn_inputs, [])

    def test_invalid_idle_budget_refuses_before_native_launch(self):
        self.runner.transport = InitialStatusTransport
        before = len(FakeServer.calls)
        with patch.dict(
            "os.environ", {"LAOMEDO_CODEX_IDLE_SESSION_SECONDS": "invalid"}
        ):
            result = self.runner.start(self.request())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(
            result["error_category"], "runner_transport_configuration_invalid"
        )
        self.assertEqual(len(FakeServer.calls), before)
        self.assertFalse(self.runner.has_live_session(result["run_id"]))

    def test_expired_session_is_refused_before_the_watcher_observes_it(self):
        self.runner.transport = InitialStatusTransport
        result = self.runner.start(self.request())
        held = self.runner._idle_sessions[result["run_id"]]
        held.expires = time.monotonic() - 1
        following = self.runner.resume(
            result["run_id"],
            "Do not dispatch",
            expected_thread_id=result["thread_id"],
            expected_post_run_hash=result["post_run_hash"],
            model="test-model",
            effort="low",
        )
        self.assertEqual(following["status"], "failed")
        self.assertEqual(following["error_category"], "codex_idle_session_unavailable")
        self.assertTrue(held.runtime.log.closed)
        self.assertFalse(self.runner.has_live_session(result["run_id"]))
        self.assertEqual(FakeServer.turn_inputs, [])

    def test_missing_native_command_capability_refuses_before_model_prompt(self):
        result = self.runner.start(self.request())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_category"], "native_command_not_supported")
        self.assertEqual(FakeServer.turn_inputs, [])

    def test_other_providers_default_refusal_and_codex_exact_initial_mode(self):
        with self.assertRaisesRegex(RunnerError, "native_command_not_supported"):
            BaseAgent.prepare_initial_command(self.runner, self.request())
        for change in (
            {"initial_native_command": "review"},
            {"task": "Please run /status"},
            {"github_authorization_ref": "scope"},
            {"output_requirements": {}},
        ):
            with self.subTest(change=change), self.assertRaises(RunnerError):
                self.runner.start({**self.request(), **change})
        self.assertEqual(FakeServer.turn_inputs, [])

    def _authenticated_status(self):
        self.runner.transport = InitialStatusTransport
        identity = {
            "credential_ref": "fixture-account",
            "provider_subject_hash": "fixture-subject",
            "generation": 1,
            "auth_outcome": "active",
        }
        self.runner.auth = Mock()
        self.runner.auth.access_token.return_value = ("fixture-initial-token", identity)
        self.runner.auth.account.return_value = {"state": "active"}
        self.runner.auth.summary.return_value = identity
        return self.runner.start(self.request()), identity
