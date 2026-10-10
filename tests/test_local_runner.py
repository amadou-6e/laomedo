"""Credential-free runner and pinned-skill contract tests."""

from pathlib import Path
from contextlib import nullcontext
import io
import json
import multiprocessing
import os
import queue
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib import request as http_request, error as http_error

from laomedo.local_runner import (AppServer, SplitAppServer, LocalRunner, RunnerError,
                                  _docker_prefix, _hash_tree, _copy_tree,
                                  _native_error_summary,
                                  serve)
from laomedo.siwc_auth import AuthError
from laomedo.skill_store import SkillStore
from laomedo.mediation_authority import RunGrantAuthority


def _serve_synthetic_host_services(state: str, token_file: str, checkout: str) -> None:
    """Real lease/mediator processes, but no Docker or provider call."""
    from unittest.mock import patch as child_patch
    from laomedo.host_services import build_services, serve_services
    from laomedo import lease_service

    root = Path(state)
    lease, mediator = build_services(
        state=root, repository="example/disposable", checkout=Path(checkout),
        baseline="a" * 40, agent_mount=Path(checkout),
        connection_id="synthetic", connection_generation=1,
        token_file=Path(token_file))
    with child_patch.object(lease_service, "inspect_exact",
                            return_value=("absent", None)):
        serve_services(lease, mediator, root, repository="example/disposable",
                       connection_id="synthetic", connection_generation=1)


class FakeServer:
    calls = []
    turn_inputs = []

    def __init__(self, command, evidence):
        self.command = command
        self.evidence = evidence
        self.events = []
        self.resume = False
        self.log = (evidence / "raw-events.jsonl").open("a", encoding="utf-8")
        self.log.write('{"method":"initialized"}\n')
        self.log.flush()
        self.calls.append(command)

    def request(self, method, params, timeout=30):
        if method == "initialize":
            return {"result": {}}
        if method == "model/list":
            return {"result": {"data": [{"id": "test-model",
                "supportedReasoningEfforts": ["low"]}]}}
        if method == "thread/start":
            return {"result": {"thread": {"id": "native-thread"}}}
        if method == "thread/resume":
            self.resume = True
            assert params["threadId"] == "native-thread"
            return {"result": {"thread": {"id": "native-thread"}}}
        if method == "turn/start":
            self.turn_inputs.append(params["input"][0]["text"])
            return {"result": {"turn": {"id": "turn-2" if self.resume else "turn-1"}}}
        raise AssertionError(method)

    def notify(self, method, params):
        pass

    def wait_turn(self, turn_id, timeout, cancelled):
        workspace = self.evidence / "workspace"
        if self.resume:
            assert (workspace / "agent.txt").read_text() == "from-first-turn"
        else:
            assert not (workspace / "agent.txt").exists()
            (workspace / "agent.txt").write_text("from-first-turn")
        self.events.append({"method": "item/completed", "params": {"item": {
            "type": "agentMessage", "text": "synthetic answer"}}})
        self.log.write('{"method":"turn/completed"}\n')
        self.log.flush()
        return "completed", None

    def close(self):
        self.log.close()


class LocalRunnerTests(unittest.TestCase):
    def _output_run(self, answers, *, effects=False, cap=6, retry_count=1):
        from laomedo.output_contract import requirements
        pinned = requirements({"schema_version": 1, "fields": [
            {"name": "report", "type": "string", "required": True}]})
        class OutputServer(FakeServer):
            inputs, thread_params = [], []
            def request(inner, method, params, timeout=30):
                if method == "thread/start":
                    inner.thread_params.append(params)
                if method == "turn/start":
                    inner.inputs.append(params)
                    return {"result": {"turn": {"id": "output-" + str(len(inner.inputs))}}}
                return super().request(method, params, timeout)
            def wait_turn(inner, turn_id, timeout, cancelled):
                if effects:
                    inner.events.append({"method": "item/completed", "params": {
                        "turnId": turn_id, "item": {"type": "fileChange", "id": "effect"}}})
                answer = answers[min(len(inner.inputs) - 1, len(answers) - 1)]
                if answer is not None:
                    inner.events.append({"method": "item/completed", "params": {
                        "turnId": turn_id, "item": {"type": "agentMessage", "text": json.dumps(answer)}}})
                return "completed", None
        self.runner.transport = OutputServer
        self.runner.max_model_turns = cap
        request = self.request()
        request.update(output_requirements=pinned, output_retries=retry_count)
        return self.runner.start(request), OutputServer

    def test_output_continuation_is_same_thread_feedback_only_and_ledger_counted(self):
        record, transport = self._output_run([{}, {"report": "fixed", "task_outcome": "success"}])
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["output_validation"]["contract_status"], "accepted")
        self.assertEqual(record["output_correction_count"], 1)
        self.assertEqual(record["attempt_number"], 2)
        self.assertEqual(len(record["turns"]), 2)
        self.assertEqual([item["threadId"] for item in transport.inputs], ["native-thread"] * 2)
        self.assertNotIn("Use the sample skill", transport.inputs[1]["input"][0]["text"])
        self.assertEqual(transport.thread_params[0]["dynamicTools"][0]["name"], "laomedo_output_precheck")

    def test_output_correction_exhaustion_remains_rejected_without_third_turn(self):
        record, transport = self._output_run([{}, {}])
        self.assertEqual(len(transport.inputs), 2)
        self.assertEqual(record["output_validation"]["contract_status"], "rejected")

    def test_explicit_agent_failure_does_not_trigger_output_retry(self):
        record, transport = self._output_run([{"task_outcome": "failure"}])
        self.assertEqual(len(transport.inputs), 1)
        self.assertEqual(record["output_validation"]["contract_status"], "rejected")

    def test_side_effect_and_exhausted_global_budget_prevent_continuation(self):
        record, transport = self._output_run([{}], effects=True)
        self.assertEqual(len(transport.inputs), 1)
        self.assertEqual(record["output_correction_blocked"], "side_effect_safety_unverified")
        record, transport = self._output_run([{}], cap=1)
        self.assertEqual(len(transport.inputs), 0)  # prior run used the single authorized turn
        self.assertEqual(record["error_category"], "model_turn_cap_reached")

    def test_empty_continuation_never_uses_previous_turn_answer(self):
        record, transport = self._output_run([{}, None])
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["error_category"], "completed_without_agent_message")

    def test_global_budget_exhaustion_keeps_invalid_result_without_dispatch(self):
        record, transport = self._output_run([{}], cap=1)
        self.assertEqual(len(transport.inputs), 1)
        self.assertEqual(record["output_correction_blocked"], "model_turn_cap_reached")
        self.assertEqual(len(record["turns"]), 1)
        self.assertEqual(record["output_validation"]["contract_status"], "rejected")

    def test_zero_correction_count_and_no_fabricated_precheck_call(self):
        record, transport = self._output_run([{}], retry_count=0)
        self.assertEqual(len(transport.inputs), 1)
        self.assertEqual(record["precheck"], {"installed": True, "call_count": 0})

    def test_exact_run_capability_is_redacted_before_trace_persistence(self):
        app = AppServer.__new__(AppServer)
        app.secret_redactions = ("synthetic-run-capability",)
        output = app._redact('{"text":"synthetic-run-capability"}\n')
        self.assertEqual(output, '{"text":"[REDACTED_RUN_CAPABILITY]"}\n')

    def test_real_lease_mediated_execute_and_stale_mediator_refusal(self):
        host_state = self.runner.state / "host-services"
        token_file = self.runner.state / "private.env"
        token_file.write_text("GH=synthetic-provider-secret\n", encoding="utf-8")
        child = multiprocessing.get_context("spawn").Process(
            target=_serve_synthetic_host_services,
            args=(str(host_state), str(token_file), str(self.source)))
        child.start()
        try:
            deadline = time.monotonic() + 10
            while not all(path.exists() for path in (
                    host_state / "lease" / "service.json",
                    host_state / "lease" / "service.alive",
                    host_state / "lease" / "service.alive.monotonic",
                    host_state / "mediator" / "mediator.json")):
                if time.monotonic() > deadline or not child.is_alive():
                    self.fail("synthetic host services did not start")
                time.sleep(.02)
            authority = RunGrantAuthority(
                host_state / "authority.sqlite",
                connection_authorizer=lambda cid, gen, repo, reviewer:
                (cid, gen, repo, reviewer) ==
                ("synthetic", 1, "example/disposable", "operator"))
            mediated = LocalRunner(
                self.runner.state, self.runner.store.root, self.source,
                transport=FakeServer, check_docker=False, max_model_turns=6,
                supervise_containers=True, lease_service=host_state / "lease",
                github_authority=authority, mediator_state=host_state / "mediator")

            def prepare(number):
                reference = authority.approve(
                    invocation_id=f"invocation-{number}",
                    repository="example/disposable", branch=f"branch-{number}",
                    operations={"actions_read"}, reviewed_by="operator",
                    connection_id="synthetic", connection_generation=1)
                request = self.request()
                request["github_authorization_ref"] = reference
                return mediated._prepare(request)

            FakeServer.calls.clear()
            FakeServer.turn_inputs.clear()
            if os.name != "nt":
                # The CI success path below substitutes a fake route. First
                # assert that the actual Linux route fails before dispatch.
                unverified = prepare("unverified")
                with patch("laomedo.local_runner.cleanup_exact",
                           return_value=(True, "absent")):
                    refused = mediated._execute(
                        unverified["run_id"], "Synthetic task", resume=False)
                self.assertEqual(refused["status"], "failed")
                self.assertEqual(refused["error_category"],
                                 "mediator_container_route_unverified")
                self.assertEqual(FakeServer.calls, [])
            # Linux CI has no verified container-to-host route. Exercise the
            # real lease/runner path with a fake transport while preserving
            # the same live instance check; Windows tests the actual route.
            def ci_route():
                status = json.loads((host_state / "mediator" / "mediator.json").read_text())
                with http_request.urlopen(
                        f"http://127.0.0.1:{status['port']}/v1/health",
                        timeout=2) as response:
                    health = json.load(response)
                if health != {"status": "ready", "instance": status["instance"]}:
                    raise RunnerError("mediator_unavailable")
                return (f"http://host.docker.internal:{status['port']}/v1/mediate",
                        status["instance"])

            route_check = (nullcontext() if os.name == "nt" else
                           patch.object(mediated, "_mediator_route", side_effect=ci_route))
            with route_check:
                prepared = prepare(1)
                with patch("laomedo.local_runner.cleanup_exact", return_value=(True, "absent")):
                    result = mediated._execute(prepared["run_id"], "Synthetic task", resume=False)
                self.assertEqual(result["status"], "completed", result.get("error_category"))
                self.assertEqual(len(FakeServer.calls), 1)
                command = " ".join(FakeServer.calls[0])
                self.assertIn("target=/run/laomedo/capability,readonly", command)
                self.assertIn("host.docker.internal", command)
                self.assertNotIn("synthetic-provider-secret", command)
                self.assertIn("node /run/laomedo/mediate.mjs", FakeServer.turn_inputs[0])
                lease_dir = host_state / "lease" / "leases" / result["container_ownership"]["launch_token"]
                self.assertEqual(json.loads((lease_dir / "result.json").read_text())["reason"], "done")

                prepared = prepare(2)
                status_path = host_state / "mediator" / "mediator.json"
                status = json.loads(status_path.read_text(encoding="utf-8"))
                status_path.write_text(json.dumps({**status, "instance": "0" * 32}),
                                       encoding="utf-8")
                with patch("laomedo.local_runner.cleanup_exact", return_value=(True, "absent")):
                    result = mediated._execute(prepared["run_id"], "Synthetic task", resume=False)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["error_category"], "mediator_unavailable")
                self.assertEqual(len(FakeServer.calls), 1)
                lease_dir = host_state / "lease" / "leases" / result["container_ownership"]["launch_token"]
                self.assertEqual(json.loads((lease_dir / "result.json").read_text())["reason"], "done")
        finally:
            child.terminate()
            child.join(timeout=5)
    def test_mediator_mount_contains_capability_not_provider_token(self):
        capability = self.runner.state / "grant.secret"
        capability.write_text("synthetic-run-capability", encoding="utf-8")
        command = _docker_prefix(self.root / "source", self.root / "source",
                                 self.runner.state, capability=capability,
                                 mediator_url="http://host.docker.internal:1234/v1/mediate",
                                 mediator_instance="a" * 32)
        joined = " ".join(command)
        self.assertIn("source=" + str(capability), joined)
        self.assertIn("target=/run/laomedo/capability,readonly", joined)
        self.assertIn("LAOMEDO_MEDIATOR_URL=http://host.docker.internal:1234/v1/mediate",
                      joined)
        self.assertIn("LAOMEDO_MEDIATOR_INSTANCE=" + "a" * 32, joined)
        self.assertNotIn("synthetic-run-capability", joined)
        self.assertNotIn("GH_TOKEN", joined)
        with self.assertRaisesRegex(RunnerError, "incomplete_mediator_mount"):
            _docker_prefix(self.root, self.root, self.root, capability=capability)

    def test_split_executor_cannot_claim_legacy_container_lease(self):
        with self.assertRaisesRegex(RunnerError, "split_executor_lease_unavailable"):
            LocalRunner(self.runner.state, self.runner.store.root, self.source,
                        check_docker=False, split_executor=True,
                        supervise_containers=True)

    def test_git_image_trusts_only_fixed_workspace_for_native_git(self):
        from laomedo.local_runner import GIT_IMAGE, GIT_IMAGE_ID
        args = (self.root / "source", self.root / "source", self.runner.state)
        command = _docker_prefix(*args, image=GIT_IMAGE)
        entries = [command[index + 1] for index, item in enumerate(command[:-1])
                   if item == "--env" and command[index + 1].startswith("GIT_CONFIG_")]
        self.assertEqual(entries, ["GIT_CONFIG_COUNT=1",
                                  "GIT_CONFIG_KEY_0=safe.directory",
                                  "GIT_CONFIG_VALUE_0=/draft"])
        self.assertNotIn("GIT_CONFIG_COUNT=1", _docker_prefix(*args))
        pinned = _docker_prefix(*args, image=GIT_IMAGE_ID)
        self.assertEqual([pinned[index + 1] for index, item in enumerate(pinned[:-1])
                          if item == "--env" and pinned[index + 1].startswith("GIT_CONFIG_")],
                         entries)

    def test_container_identity_is_saved_before_transport_launch(self):
        class InspectReservation(FakeServer):
            def __init__(self, command, evidence):
                saved = json.loads((evidence / "record.json").read_text(encoding="utf-8"))
                owner = saved["container_ownership"]
                assert saved["status"] == "running"
                assert command[command.index("--name") + 1] == owner["name"]
                assert "laomedo.run_id=" + saved["run_id"] in command
                assert "laomedo.launch_token=" + owner["launch_token"] in command
                super().__init__(command, evidence)

        self.runner.transport = InspectReservation
        result = self.runner.start(self.request())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["container_ownership"]["supervised"], False)

    def test_supervised_launch_refuses_without_independent_lease_service(self):
        launched = []

        class Recording(FakeServer):
            def __init__(self, command, evidence):
                launched.append(command)
                super().__init__(command, evidence)

        self.runner.transport = Recording
        self.runner.supervise_containers = True
        result = self.runner.start(self.request())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_category"], "lease_service_required")
        self.assertEqual(launched, [])

    def test_mediated_scope_requires_trusted_one_run_authorization(self):
        authority = RunGrantAuthority(self.runner.state / "github-authority.sqlite")
        reference = authority.approve(
            invocation_id="approved-invocation", repository="example/disposable",
            branch="approved-branch", operations={"actions_read"},
            reviewed_by="test-operator")
        request = self.request()
        request["github_scope"] = {"repository": "other/repo"}
        with self.assertRaisesRegex(RunnerError, "github_scope_must_come_from_authority"):
            self.runner._prepare(request)
        request.pop("github_scope")
        request["github_authorization_ref"] = reference
        with self.assertRaisesRegex(RunnerError, "mediated_lease_required"):
            self.runner._prepare(request)

        mediated = LocalRunner(self.runner.state, self.runner.store.root, self.source,
                               transport=FakeServer, check_docker=False,
                               max_model_turns=6, supervise_containers=True,
                               lease_service=self.root / "lease-state",
                               github_authority=authority,
                               mediator_state=self.runner.state / "mediator-state")
        prepared = mediated._prepare(request)
        self.assertEqual(prepared["github_scope"], {
            "invocation_id": "approved-invocation",
            "repository": "example/disposable", "branch": "approved-branch"})
        self.assertNotIn(reference, json.dumps(prepared))
        with self.assertRaisesRegex(RunnerError, "authorization_unavailable"):
            mediated._prepare(request)

        push_ref = authority.approve(
            invocation_id="push-invocation", repository="example/disposable",
            branch="approved-branch", operations={"git_push"},
            reviewed_by="test-operator")
        request["github_authorization_ref"] = push_ref
        with self.assertRaisesRegex(RunnerError, "operation_unavailable_in_runner"):
            mediated._prepare(request)

    def test_restart_sweep_preserves_unverified_cleanup(self):
        record = self.runner._prepare(self.request())
        path = self.runner._run_dir(record["run_id"]) / "record.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        saved["status"] = "running"
        saved["container_ownership"] = {"name": "exact-name",
                                         "launch_token": "token-one", "supervised": True,
                                         "cleanup_verified": False}
        path.write_text(json.dumps(saved), encoding="utf-8")
        with patch("laomedo.local_runner.cleanup_exact", return_value=(False, "conflict")) as cleanup:
            restarted = LocalRunner(self.runner.state, self.runner.store.root, self.source,
                                    transport=FakeServer, check_docker=False)
        after = restarted.status(record["run_id"])
        self.assertEqual(after["status"], "interrupted")
        self.assertEqual(after["error_category"], "container_cleanup_unverified")
        self.assertFalse(after["container_ownership"]["cleanup_verified"])
        cleanup.assert_called_once_with("exact-name", record["run_id"], "token-one")

    def test_native_error_summary_only_exposes_schema_codes(self):
        secret = "SECRET_LOGIN_TOKEN_and_https://private.example/path"
        events = [
            {"method": "error", "params": {"turnId": "wanted", "willRetry": True,
                "error": {"message": secret, "additionalDetails": secret,
                    "codexErrorInfo": {"httpConnectionFailed": {
                        "httpStatusCode": 401, "url": secret}}}}},
            {"method": "error", "params": {"turnId": "wanted", "willRetry": False,
                "error": {"message": secret, "codexErrorInfo": secret}}},
            {"method": "error", "params": {"turnId": "other", "error": {
                "codexErrorInfo": "unauthorized", "message": secret}}},
        ]
        summary = _native_error_summary(events, "wanted")
        self.assertEqual(summary, {"schema_version": 1, "error_events": 2,
            "retry_events": 1, "categories": {"httpConnectionFailed": 1,
            "unknown": 1}, "http_status_codes": [401],
            "last_category": "unknown"})
        self.assertNotIn(secret, json.dumps(summary))

    def test_failed_native_turn_exposes_only_allowlisted_category(self):
        class Failed(FakeServer):
            def wait_turn(self, turn_id, timeout, cancelled):
                self.events.append({"method": "error", "params": {
                    "turnId": turn_id, "willRetry": False, "error": {
                        "codexErrorInfo": "unauthorized",
                        "message": "SECRET_LOGIN_TOKEN_and_https://private.example/path"}}})
                return "failed", None

        self.runner.transport = Failed
        result = self.runner.start(self.request())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_category"], "codex_unauthorized")
        self.assertEqual(result["native_error_summary"]["categories"],
                         {"unauthorized": 1})
        self.assertNotIn("SECRET_LOGIN_TOKEN", json.dumps(result))
        self.assertEqual(json.loads((self.runner.state / "turn-ledger.json").read_text())
                         ["attempted_turns"], 1)

    def test_missing_app_owned_consent_refuses_before_model_turn(self):
        class MissingAccount:
            def access_token(self):
                raise AuthError("auth_account_missing")

        self.runner.auth = MissingAccount()
        result = self.runner.start(self.request())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_category"], "auth_missing")
        self.assertEqual(result["credential"]["credential_mode"],
                         "chatgpt_plan_oauth")
        self.assertEqual(result["credential"]["auth_outcome"], "missing")
        self.assertEqual(result["turns"], [])
        self.assertFalse((self.runner.state / "turn-ledger.json").exists())

    def test_split_selection_refuses_missing_ambiguous_or_wrong_executor(self):
        server = SimpleNamespace(environment_id="private-executor")
        good = [{"environmentId": "private-executor", "cwd": "/draft"}]
        SplitAppServer.assert_executor_selection(server, good)
        for bad in ([], [{}], [{"environmentId": "other", "cwd": "/draft"}],
                    [{"environmentId": "private-executor", "cwd": "/"}],
                    good + good):
            with self.subTest(selection=bad):
                with self.assertRaisesRegex(RunnerError,
                                            "^executor_selection_mismatch$"):
                    SplitAppServer.assert_executor_selection(server, bad)

    def test_split_wait_turn_revocation_interrupts_without_completion(self):
        server = SimpleNamespace(events=[{"method": "item/completed",
            "params": {"item": {"type": "commandExecution"}}}],
            authorization_probe=lambda: False, interrupt=Mock())
        status, error = SplitAppServer.wait_turn(
            server, "native-turn", 1, threading.Event())
        self.assertEqual((status, error), ("unknown", "auth_revoked_during_turn"))
        server.interrupt.assert_called_once_with("native-turn")

    def test_mid_turn_revocation_retains_turn_ledger_and_partial_trace(self):
        state = {"active": True}

        class ConnectedAccount:
            def access_token(self):
                return "SYNTHETIC", {"credential_ref": "chatgpt:fixture",
                    "provider_subject_hash": "sha256:fixture", "generation": 1,
                    "auth_outcome": "active"}

            def active(self):
                return {"state": "active" if state["active"] else "revoked"}

            def summary(self, _account):
                return {"credential_ref": "chatgpt:fixture",
                    "provider_subject_hash": "sha256:fixture", "generation": 1,
                    "auth_outcome": "active"}

        class RevokedDuringTurn(FakeServer):
            def wait_turn(self, turn_id, timeout, cancelled):
                self.events.append({"method": "item/completed", "params": {
                    "item": {"type": "commandExecution", "exitCode": 0}}})
                self.log.write('{"method":"item/completed"}\n')
                self.log.flush()
                state["active"] = False
                assert not self.authorization_probe()
                return "unknown", "auth_revoked_during_turn"

        self.runner.transport = RevokedDuringTurn
        self.runner.auth = ConnectedAccount()
        result = self.runner.start(self.request())
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["error_category"], "auth_revoked_during_turn")
        self.assertEqual(result["credential"]["auth_outcome"], "revoked")
        self.assertEqual(result["attempt_number"], 1)
        self.assertEqual(result["turns"][0]["status"], "unknown")
        self.assertTrue((self.runner._run_dir(result["run_id"]) /
                         "raw-events.jsonl").exists())
        self.assertEqual(json.loads((self.runner.state / "turn-ledger.json")
                         .read_text())["attempted_turns"], 1)

    def test_mid_turn_account_or_generation_change_is_not_reported_as_revocation(self):
        for change, expected_error, expected_outcome in (
                ("account", "auth_account_changed_during_turn", "account_mismatch"),
                ("generation", "auth_generation_changed_during_turn",
                 "generation_changed")):
            state = {"credential_ref": "chatgpt:fixture", "generation": 1}

            class ConnectedAccount:
                def access_token(self):
                    return "SYNTHETIC", {"credential_ref": "chatgpt:fixture",
                        "provider_subject_hash": "sha256:fixture", "generation": 1,
                        "auth_outcome": "active"}

                def active(self):
                    return {"state": "active"}

                def summary(self, _account):
                    return {"credential_ref": state["credential_ref"],
                        "provider_subject_hash": "sha256:fixture",
                        "generation": state["generation"], "auth_outcome": "active"}

            class ChangedDuringTurn(FakeServer):
                def wait_turn(self, turn_id, timeout, cancelled):
                    self.events.append({"method": "item/completed", "params": {
                        "item": {"type": "commandExecution", "exitCode": 0}}})
                    state["credential_ref" if change == "account" else
                          "generation"] = ("chatgpt:other" if change == "account"
                                           else 2)
                    assert not self.authorization_probe()
                    return "unknown", "auth_revoked_during_turn"

            self.runner.transport = ChangedDuringTurn
            self.runner.auth = ConnectedAccount()
            result = self.runner.start(self.request())
            with self.subTest(change=change):
                self.assertEqual(result["status"], "unknown")
                self.assertEqual(result["error_category"], expected_error)
                self.assertEqual(result["credential"]["auth_outcome"],
                                 expected_outcome)
                self.assertEqual(result["turns"][0]["error_category"],
                                 expected_error)
        self.assertEqual(json.loads((self.runner.state / "turn-ledger.json")
                         .read_text())["attempted_turns"], 2)

    def test_generation_change_before_turn_refuses_without_model_submission(self):
        class ChangedBeforeTurn(FakeServer):
            turn_starts = 0

            def request(self, method, params, timeout=30):
                if method == "turn/start":
                    type(self).turn_starts += 1
                return super().request(method, params, timeout)

        class Account:
            def access_token(self):
                return "SYNTHETIC", {"credential_ref": "chatgpt:fixture",
                    "provider_subject_hash": "sha256:fixture", "generation": 1,
                    "auth_outcome": "active"}

            def active(self):
                return {"state": "active"}

            def summary(self, _account):
                return {"credential_ref": "chatgpt:fixture",
                    "provider_subject_hash": "sha256:fixture", "generation": 2,
                    "auth_outcome": "active"}

        self.runner.transport = ChangedBeforeTurn
        self.runner.auth = Account()
        result = self.runner.start(self.request())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_category"], "auth_generation_changed")
        self.assertEqual(result["credential"]["auth_outcome"],
                         "generation_changed")
        self.assertEqual(result["turns"], [])
        self.assertEqual(ChangedBeforeTurn.turn_starts, 0)

    def test_mid_turn_refresh_uncertainty_stays_distinct_from_revocation(self):
        state = {"value": "active"}

        class Account:
            def access_token(self):
                return "SYNTHETIC", {"credential_ref": "chatgpt:fixture",
                    "provider_subject_hash": "sha256:fixture", "generation": 1,
                    "auth_outcome": "active"}

            def active(self):
                return {"state": state["value"]}

            def summary(self, _account):
                return {"credential_ref": "chatgpt:fixture",
                    "provider_subject_hash": "sha256:fixture", "generation": 1,
                    "auth_outcome": state["value"]}

        class RefreshUnknown(FakeServer):
            def wait_turn(self, turn_id, timeout, cancelled):
                state["value"] = "refresh_unknown"
                assert not self.authorization_probe()
                return "unknown", "auth_revoked_during_turn"

        self.runner.transport = RefreshUnknown
        self.runner.auth = Account()
        result = self.runner.start(self.request())
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["error_category"], "auth_refresh_failed_during_turn")
        self.assertEqual(result["credential"]["auth_outcome"], "refresh_unknown")
        self.assertEqual(result["attempt_number"], 1)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "task.txt").write_text("source input")
        (self.root / ".git").mkdir()
        self.skill_source = self.root / "skill-source"
        self.skill_source.mkdir()
        (self.skill_source / "SKILL.md").write_text("---\nname: sample\n---\nUse amber.\n")
        store = SkillStore(self.root.parent / (self.root.name + "-skill-store"))
        self.addCleanup(lambda: __import__("shutil").rmtree(store.root.parent /
                        (self.root.name + "-skill-store"), ignore_errors=True))
        self.addCleanup(lambda: __import__("shutil").rmtree(store.draft_root,
                        ignore_errors=True))
        self.revision = store.import_skill("sample", self.skill_source)
        self.runner = LocalRunner(self.root.parent / (self.root.name + "-state"),
                                  store.root, self.source, transport=FakeServer,
                                  check_docker=False, max_model_turns=6)
        self.addCleanup(lambda: __import__("shutil").rmtree(self.runner.state,
                        ignore_errors=True))

    def request(self):
        return {"task": "Use the sample skill", "model": "test-model",
                "effort": "low",
                "skill_ref": {"skill_id": "sample",
                              "revision_id": self.revision["revision_id"],
                              "tree_hash": self.revision["tree_hash"]}}

    def test_opt_in_git_workspace_preserves_agent_history_without_snapshotting_it(self):
        repository = self.root / "git-source"
        repository.mkdir()
        (repository / "task.txt").write_text("source input", encoding="utf-8")

        def git(*args, cwd=repository):
            result = __import__("subprocess").run(
                ["git", "-C", str(cwd), *args], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.decode().strip()

        git("init", "-q")
        git("add", "task.txt")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "commit", "-qm", "baseline")
        baseline = git("rev-parse", "HEAD")
        runner = LocalRunner(self.runner.state, self.runner.store.root, repository,
                             transport=FakeServer, check_docker=False,
                             max_model_turns=6, git_workspace=True)
        result = runner.start(self.request())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["workspace_mode"], "git")
        self.assertEqual(result["image"], "laomedo-codex-git:0.159.2")
        self.assertIn("sha256:eceda79a349c46a8afd6fb271e92b979f872ca67cbdf228fde6dee0856481e78", FakeServer.calls[-1])
        self.assertEqual(result["git_baseline"], baseline)
        self.assertTrue(result["skill_git_exclusion"]["enabled"])
        self.assertEqual(result["post_run_hash_scope"], "working_files_only")
        run_dir = runner._run_dir(result["run_id"])
        self.assertEqual(git("rev-parse", "HEAD", cwd=run_dir / "workspace"), baseline)
        self.assertEqual(git("remote", cwd=run_dir / "workspace"), "")
        self.assertFalse((run_dir / "canonical" / ".git").exists())
        self.assertFalse((run_dir / "post-run" / ".git").exists())
        self.assertTrue((run_dir / "workspace" / ".git").is_dir())
        status = git("status", "--porcelain", cwd=run_dir / "workspace")
        self.assertIn("agent.txt", status)
        self.assertNotIn(".agents/skills", status)
        self.assertFalse((repository / "agent.txt").exists())
        resumed = runner.resume(result["run_id"], "Continue in the same repository",
                                expected_post_run_hash=result["post_run_hash"],
                                expected_thread_id=result["thread_id"],
                                model="test-model", effort="low")
        self.assertEqual(resumed["status"], "completed")
        self.assertTrue((run_dir / "workspace" / ".git").is_dir())

        authority = RunGrantAuthority(self.runner.state / "git-authority.sqlite")
        reference = authority.approve(
            invocation_id="approved-git", repository="example/disposable",
            branch="run-branch", operations={"git_push"},
            reviewed_by="test-operator")
        mediated = LocalRunner(
            self.runner.state, self.runner.store.root, repository,
            transport=FakeServer, check_docker=False, max_model_turns=6,
            git_workspace=True, supervise_containers=True,
            lease_service=self.runner.state / "lease-state",
            github_authority=authority,
            mediator_state=self.runner.state / "mediator-state")
        request = self.request()
        request["github_authorization_ref"] = reference
        prepared = mediated._prepare(request)
        self.assertEqual(prepared["github_scope"]["branch"], "run-branch")
        self.assertEqual(prepared["workspace_mode"], "git")
        private_lease = self.runner.state / "fixture-lease"
        private_lease.mkdir()
        (private_lease / "grant.secret").write_text("synthetic-capability", encoding="utf-8")
        lease = SimpleNamespace(instance="fixture-instance", grant_id="fixture-grant",
                                dir=private_lease, lost=threading.Event(), finish=Mock())
        with patch("laomedo.local_runner.LeaseClient", return_value=lease), \
                patch.object(mediated, "_mediator_route",
                             return_value=("http://host.docker.internal:1234/v1/mediate", "fixture-instance")), \
                patch("laomedo.local_runner.cleanup_exact", return_value=(True, "absent")):
            completed = mediated._execute(prepared["run_id"], "Synthetic task", resume=False)
            self.assertEqual(completed["status"], "completed", completed.get("error_category"))
            exclusion = completed["skill_git_exclusion"]
            self.assertTrue(exclusion["enabled"])
            owned_workspace = mediated._run_dir(completed["run_id"]) / "workspace"
            before = (owned_workspace / ".git/info/exclude").read_bytes()
            self.assertIn(b"/.laomedo-handoff.bundle", before.splitlines())
            self.assertEqual(completed["container_ownership"]["grant_id"], "fixture-grant")
            resumed = mediated.resume(completed["run_id"], "Continue synthetic task",
                expected_post_run_hash=completed["post_run_hash"],
                expected_thread_id=completed["thread_id"], model="test-model", effort="low")
            self.assertEqual(resumed["status"], "completed", resumed.get("error_category"))
            self.assertEqual(resumed["skill_git_exclusion"], exclusion)
            self.assertEqual((owned_workspace / ".git/info/exclude").read_bytes(), before)
        # These are mocked grants/transports, not acceptance of real renewed
        # mediated grants or a model invocation's resume lifecycle.

    def test_git_workspace_snapshot_refuses_oversized_file_before_reading_it(self):
        root = self.root / "oversized"
        root.mkdir()
        with (root / "oversized.bin").open("wb") as stream:
            stream.truncate(65 * 1024 * 1024)
        with self.assertRaisesRegex(RunnerError, "git_workspace_snapshot_limit"):
            _hash_tree(root, exclude_root_git=True)

    def test_git_snapshot_excludes_only_exact_metadata_directory(self):
        root = self.root / "case-variant"
        root.mkdir()
        variant = root / ".GIT"
        variant.mkdir()
        payload = variant / "ordinary.txt"
        payload.write_text("one", encoding="utf-8")
        first = _hash_tree(root, exclude_root_git=True)
        payload.write_text("two", encoding="utf-8")
        self.assertNotEqual(first, _hash_tree(root, exclude_root_git=True))
        copied = self.root / "case-variant-copy"
        _copy_tree(root, copied, exclude_root_git=True)
        self.assertEqual((copied / ".GIT" / "ordinary.txt").read_text(), "two")

    def auth_headers(self, *, content_type="application/json"):
        return {"Authorization": "Bearer " + self.runner.api_token,
                "Content-Type": content_type}

    def test_start_resume_and_fresh_workspace(self):
        first = self.runner.start(self.request())
        self.assertEqual(first["status"], "completed")
        self.assertEqual(first["thread_id"], "native-thread")
        self.assertEqual(first["skill"]["use_evidence"], "offered")
        self.assertEqual(first["answer"], "synthetic answer")
        command = FakeServer.calls[-1]
        self.assertIn("type=volume,source=laomedo-122-docker-auth,target=/home/runner/.codex",
                      command)
        self.assertNotIn("auth.json", " ".join(command))
        output = self.runner._run_dir(first["run_id"]) / "post-run"
        self.assertEqual(_hash_tree(output), first["post_run_hash"])
        self.assertFalse((self.source / "agent.txt").exists())
        self.assertEqual((output / ".agents/skills/sample/SKILL.md").read_text(),
                         (self.skill_source / "SKILL.md").read_text())
        second = self.runner.start(self.request())
        self.assertNotEqual(second["run_id"], first["run_id"])
        restarted = LocalRunner(self.runner.state, self.runner.store.root, self.source,
                                 transport=FakeServer, check_docker=False,
                                 max_model_turns=6)
        resumed = restarted.resume(first["run_id"], "continue",
                                   expected_post_run_hash=first["post_run_hash"],
                                   expected_thread_id=first["thread_id"],
                                   model="test-model", effort="low")
        self.assertEqual(resumed["status"], "completed")
        self.assertEqual(len(resumed["turns"]), 2)
        self.assertEqual(json.loads((self.runner.state / "turn-ledger.json").read_text())
                         ["attempted_turns"], 3)

    def test_app_owned_resume_refuses_changed_account_and_runner_restart(self):
        completed = self.runner.start(self.request())
        record_path = self.runner._run_dir(completed["run_id"]) / "record.json"
        record = json.loads(record_path.read_text())
        record["credential"] = {"credential_mode": "chatgpt_plan_oauth",
                                "credential_ref": "chatgpt:first",
                                "provider_subject_hash": "sha256:first"}
        record_path.write_text(json.dumps(record))

        class OtherAccount:
            def access_token(self):
                return "synthetic", {"credential_ref": "chatgpt:second",
                                     "provider_subject_hash": "sha256:second"}

        self.runner.auth = OtherAccount()
        args = dict(expected_post_run_hash=completed["post_run_hash"],
                    expected_thread_id=completed["thread_id"],
                    model="test-model", effort="low")
        with self.assertRaisesRegex(RunnerError, "resume_auth_identity_mismatch"):
            self.runner.resume(completed["run_id"], "continue", **args)
        restarted = LocalRunner(self.runner.state, self.runner.store.root,
                                self.source, transport=FakeServer,
                                check_docker=False, max_model_turns=6)
        restarted.auth = OtherAccount()
        with self.assertRaisesRegex(RunnerError, "resume_after_runner_restart_forbidden"):
            restarted.resume(completed["run_id"], "continue", **args)
        self.assertEqual(json.loads((self.runner.state / "turn-ledger.json").read_text())
                         ["attempted_turns"], 1)

    def test_multiple_skills_materialize_and_resume_as_one_bound_snapshot(self):
        second_source = self.root / "second-skill-source"
        second_source.mkdir()
        (second_source / "SKILL.md").write_text("---\nname: second\n---\nUse amber.\n")
        second = self.runner.store.import_skill("second", second_source)
        request = self.request()
        first_ref = request.pop("skill_ref")
        request["skill_refs"] = [first_ref, {"skill_id": "second",
            "revision_id": second["revision_id"], "tree_hash": second["tree_hash"]}]
        result = self.runner.start(request)
        self.assertEqual([s["skill_id"] for s in result["skills"]], ["sample", "second"])
        self.assertIsNone(result["skill"])
        for name in ("sample", "second"):
            self.assertTrue((self.runner._run_dir(result["run_id"]) /
                             "post-run/.agents/skills" / name / "SKILL.md").is_file())
        resumed = self.runner.resume(result["run_id"], "continue",
            expected_post_run_hash=result["post_run_hash"],
            expected_thread_id=result["thread_id"], model="test-model", effort="low")
        self.assertEqual(resumed["skills"], result["skills"])

    def test_frontmatter_name_collision_fails_before_dispatch(self):
        duplicate = self.runner.store.import_skill("other-id", self.skill_source)
        request = self.request()
        request["skill_ref"] = {"skill_id": "other-id",
            "revision_id": duplicate["revision_id"], "tree_hash": duplicate["tree_hash"]}
        before = len(FakeServer.calls)
        with self.assertRaisesRegex(RunnerError, "skill_frontmatter_name_mismatch"):
            self.runner.start(request)
        self.assertEqual(len(FakeServer.calls), before)

    def test_multiple_skill_failure_cleans_partial_materialization_without_dispatch(self):
        request = self.request()
        ref = request.pop("skill_ref")
        before = len(FakeServer.calls)
        request["skill_refs"] = [ref, {**ref, "skill_id": "missing"}]
        with self.assertRaises(Exception):
            self.runner.start(request)
        self.assertEqual(len(FakeServer.calls), before)
        self.assertEqual(list((self.runner.state / "runs").iterdir()), [])
        request["skill_refs"] = [ref, ref]
        with self.assertRaisesRegex(RunnerError, "duplicate_skill_id"):
            self.runner.start(request)

    def test_default_turn_cap_denies_model_submission(self):
        stopped = LocalRunner(self.runner.state, self.runner.store.root, self.source,
                              transport=FakeServer, check_docker=False)
        result = stopped.start(self.request())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_category"], "model_turn_cap_reached")
        self.assertIsNone(result["answer"])

    def test_restart_marks_incomplete_run_interrupted_without_losing_trace(self):
        first = self.runner.start(self.request())
        run_dir = self.runner._run_dir(first["run_id"])
        record = json.loads((run_dir / "record.json").read_text())
        record["status"] = "running"
        (run_dir / "record.json").write_text(json.dumps(record))
        before = (run_dir / "raw-events.jsonl").read_bytes()
        restarted = LocalRunner(self.runner.state, self.runner.store.root, self.source,
                                 transport=FakeServer, check_docker=False)
        after = restarted.status(first["run_id"])
        self.assertEqual(after["status"], "interrupted")
        self.assertEqual(after["error_category"], "runner_restarted")
        self.assertEqual((run_dir / "raw-events.jsonl").read_bytes(), before)

    def test_missing_or_changed_snapshot_refused(self):
        first = self.runner.start(self.request())
        args = dict(expected_post_run_hash=first["post_run_hash"],
                    expected_thread_id=first["thread_id"], model="test-model", effort="low")
        with self.assertRaisesRegex(RunnerError, "resume_binding_mismatch"):
            self.runner.resume(first["run_id"], "continue", **{**args, "model": "other"})
        (self.runner._run_dir(first["run_id"]) / "post-run/task.txt").write_text("tampered")
        with self.assertRaisesRegex(RunnerError, "post_run_snapshot_mismatch"):
            self.runner.resume(first["run_id"], "continue", **args)

    def test_missing_post_run_snapshot_refused(self):
        first = self.runner.start(self.request())
        snapshot = self.runner._run_dir(first["run_id"]) / "post-run"
        __import__("shutil").rmtree(snapshot)
        with self.assertRaisesRegex(RunnerError, "post_run_snapshot_mismatch"):
            self.runner.resume(first["run_id"], "continue",
                               expected_post_run_hash=first["post_run_hash"],
                               expected_thread_id=first["thread_id"],
                               model="test-model", effort="low")

    def test_resume_binding_refusals_do_not_open_transport_or_spend_a_turn(self):
        first = self.runner.start(self.request())
        args = dict(expected_post_run_hash=first["post_run_hash"],
                    expected_thread_id=first["thread_id"], model="test-model", effort="low")
        record_path = self.runner._run_dir(first["run_id"]) / "record.json"
        original = record_path.read_bytes()
        ledger_before = (self.runner.state / "turn-ledger.json").read_bytes()
        calls_before = len(FakeServer.calls)
        for field, replacement in (("profile", "another-private-profile"),
                                   ("thread_id", "another-thread"),
                                   ("post_run_hash", "sha256:" + "0" * 64)):
            with self.subTest(field=field):
                record = json.loads(original)
                record[field] = replacement
                record_path.write_text(json.dumps(record))
                try:
                    with self.assertRaisesRegex(RunnerError, "resume_binding_mismatch"):
                        self.runner.resume(first["run_id"], "continue", **args)
                    self.assertEqual(len(FakeServer.calls), calls_before)
                    self.assertEqual((self.runner.state / "turn-ledger.json").read_bytes(), ledger_before)
                finally:
                    record_path.write_bytes(original)

    def test_empty_directory_change_invalidates_workspace_hash(self):
        first = self.runner.start(self.request())
        snapshot = self.runner._run_dir(first["run_id"]) / "post-run"
        (snapshot / "new-empty-directory").mkdir()
        self.assertNotEqual(_hash_tree(snapshot), first["post_run_hash"])

    def test_changed_canonical_mount_refuses_resume(self):
        first = self.runner.start(self.request())
        canonical = self.runner._run_dir(first["run_id"]) / "canonical/task.txt"
        canonical.write_text("changed")
        with self.assertRaisesRegex(RunnerError, "protected_mount_changed"):
            self.runner.resume(first["run_id"], "continue",
                               expected_post_run_hash=first["post_run_hash"],
                               expected_thread_id=first["thread_id"],
                               model="test-model", effort="low")

    def test_missing_and_changed_skill_revision_fail_before_turn(self):
        original = self.runner.start(self.request())
        delivered = (self.runner._run_dir(original["run_id"]) /
                     "post-run/.agents/skills/sample/SKILL.md").read_bytes()
        request = self.request()
        request["skill_ref"]["revision_id"] = "sha256:" + "0" * 64
        with self.assertRaises(RunnerError):
            self.runner.start(request)
        request = self.request()
        bundle = self.runner.store._revision_dir("sample", self.revision["revision_id"]) / "bundle"
        (bundle / "SKILL.md").write_text("tampered")
        with self.assertRaises(Exception):
            self.runner.start(request)
        self.assertEqual((self.runner._run_dir(original["run_id"]) /
                          "post-run/.agents/skills/sample/SKILL.md").read_bytes(), delivered)

    def test_skill_path_escape_refused(self):
        request = self.request()
        request["skill_ref"]["skill_id"] = "../outside"
        with self.assertRaises(Exception):
            self.runner.start(request)

    def test_http_start_and_status_keep_private_paths_out(self):
        server = serve(self.runner, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(2)))
        base = f"http://127.0.0.1:{server.server_port}/v1/runs"
        request = http_request.Request(base, data=json.dumps(self.request()).encode(),
                                       headers=self.auth_headers())
        with http_request.urlopen(request) as response:
            result = json.load(response)
        with http_request.urlopen(http_request.Request(base + "/" + result["run_id"],
                                                         headers=self.auth_headers())) as response:
            status = json.load(response)
        self.assertEqual(status["status"], "completed")
        self.assertEqual(status["raw_event_ref"],
                         f"laomedo:run:{result['run_id']}:events")
        self.assertNotIn(str(self.root), json.dumps(status))

    def test_http_rejects_unauthenticated_worker_before_read_or_turn(self):
        server = serve(self.runner, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(2)))
        base = f"http://127.0.0.1:{server.server_port}/v1/runs"
        for request in (http_request.Request(base + "/" + str(__import__("uuid").uuid4())),
                        http_request.Request(base, data=json.dumps(self.request()).encode(),
                                             headers={"Content-Type": "application/json"})):
            with self.assertRaises(http_error.HTTPError) as caught:
                http_request.urlopen(request)
            self.assertEqual(caught.exception.code, 401)
            self.assertEqual(json.load(caught.exception)["error_category"], "unauthorized")
        self.assertEqual(list((self.runner.state / "runs").iterdir()), [])
        self.assertFalse((self.runner.state / "turn-ledger.json").exists())

    def test_api_token_persists_across_runner_restart(self):
        again = LocalRunner(self.runner.state, self.runner.store.root, self.source,
                            transport=FakeServer, check_docker=False, max_model_turns=6)
        self.assertEqual(again.api_token, self.runner.api_token)
        self.assertEqual(len(self.runner.api_token), 64)

    def test_corrupt_record_does_not_hold_runner_lock(self):
        completed = self.runner.start(self.request())
        (self.runner._run_dir(completed["run_id"]) / "record.json").write_text("{")
        with self.assertRaises(ValueError):
            self.runner._execute(completed["run_id"], "retry", resume=True)
        self.assertTrue(self.runner.lock.acquire(blocking=False))
        self.runner.lock.release()

    def test_app_server_interrupt_then_removes_named_container(self):
        app = AppServer.__new__(AppServer)
        app.container_name = "laomedo-codex-test"
        app.active_thread_id = "thread-test"
        app.interrupt_acknowledged = False
        app.events = []
        app.messages = queue.Queue()
        app.request = Mock(return_value={"result": {}})
        app.process = Mock()
        app.process.poll.return_value = None
        app.reader = Mock()
        app.stderr_reader = Mock()
        app.log = io.StringIO()
        app.stderr = io.StringIO()
        cancelled = threading.Event()
        cancelled.set()
        self.assertEqual(app.wait_turn("turn-test", .05, cancelled),
                         ("cancelled", "cancel_native_unconfirmed"))
        app.request.assert_called_once_with("turn/interrupt", {
            "threadId": "thread-test", "turnId": "turn-test"}, timeout=5)
        with patch("laomedo.local_runner.subprocess.run", side_effect=[
                Mock(returncode=0), Mock(returncode=0),
                Mock(returncode=1, stderr=b"Error: No such object: laomedo-codex-test")]) as docker:
            app.close()
        self.assertEqual(docker.call_args_list[0].args[0],
                         ["docker", "rm", "-f", "laomedo-codex-test"])
        self.assertEqual(docker.call_args_list[2].args[0],
                         ["docker", "inspect", "laomedo-codex-test"])

    def test_unverified_container_removal_fails_closed(self):
        app = AppServer.__new__(AppServer)
        app.container_name = "laomedo-codex-test"
        app.process = Mock()
        app.process.poll.return_value = None
        app.reader = Mock()
        app.stderr_reader = Mock()
        app.log = io.StringIO()
        app.stderr = io.StringIO()
        with patch("laomedo.local_runner.subprocess.run", side_effect=[
                Mock(returncode=1), Mock(returncode=1), Mock(returncode=0)]):
            with self.assertRaisesRegex(RunnerError, "container_termination_unverified"):
                app.close()

    def test_http_rejects_simple_cross_origin_content_type(self):
        server = serve(self.runner, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(2)))
        req = http_request.Request(f"http://127.0.0.1:{server.server_port}/v1/runs",
                                   data=json.dumps(self.request()).encode(),
                                   headers=self.auth_headers(content_type="text/plain"))
        with self.assertRaises(http_error.HTTPError) as caught:
            http_request.urlopen(req)
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(json.load(caught.exception)["error_category"],
                         "json_content_type_required")

    def test_http_failure_preserves_run_id_and_partial_events(self):
        class TimedOut(FakeServer):
            def wait_turn(self, turn_id, timeout, cancelled):
                self.log.write('{"method":"item/started"}\n')
                self.log.flush()
                return "timeout", "turn_timeout"

        self.runner.transport = TimedOut
        server = serve(self.runner, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(2)))
        req = http_request.Request(f"http://127.0.0.1:{server.server_port}/v1/runs",
                                   data=json.dumps(self.request()).encode(),
                                   headers=self.auth_headers())
        with self.assertRaises(http_error.HTTPError) as caught:
            http_request.urlopen(req)
        self.assertEqual(caught.exception.code, 502)
        result = json.load(caught.exception)
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["error_category"], "turn_timeout")
        self.assertIsNone(result["answer"])
        self.assertIn("item/started", (self.runner._run_dir(result["run_id"]) /
                                       "raw-events.jsonl").read_text())

    def test_http_cancel_marks_running_turn_and_retains_partial_events(self):
        started = threading.Event()

        class Blocking(FakeServer):
            def wait_turn(self, turn_id, timeout, cancelled):
                self.log.write('{"method":"item/started"}\n')
                self.log.flush()
                started.set()
                assert cancelled.wait(3)
                return "cancelled", "cancelled_by_user"

        self.runner.transport = Blocking
        server = serve(self.runner, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(2)))
        base = f"http://127.0.0.1:{server.server_port}/v1/runs"
        result = {}

        def submit():
            req = http_request.Request(base, data=json.dumps(self.request()).encode(),
                                       headers=self.auth_headers())
            try:
                http_request.urlopen(req)
            except http_error.HTTPError as exc:
                result.update(json.load(exc))

        submitting = threading.Thread(target=submit)
        submitting.start()
        self.assertTrue(started.wait(2))
        run_dir = next((self.runner.state / "runs").iterdir())
        req = http_request.Request(base + "/" + run_dir.name + "/cancel",
                                   data=b"{}", method="POST",
                                   headers=self.auth_headers())
        with http_request.urlopen(req) as response:
            self.assertEqual(response.status, 202)
            self.assertTrue(json.load(response)["cancel_requested"])
        submitting.join(3)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["run_id"], run_dir.name)
        self.assertIn("item/started", (run_dir / "raw-events.jsonl").read_text())

    def test_completion_queued_before_turn_start_response_is_observed(self):
        server = AppServer.__new__(AppServer)
        server.events = [{"method": "turn/completed", "params": {"turn": {
            "id": "fast-turn", "status": "completed"}}}]
        status, error = server.wait_turn("fast-turn", .1, threading.Event())
        self.assertEqual((status, error), ("completed", None))


    def test_cancel_waits_for_native_interrupted_completion(self):
        server = AppServer.__new__(AppServer)
        server.events = []
        server.messages = queue.Queue()
        server.process = Mock()
        server.process.poll.return_value = None
        server.active_thread_id = "thread-test"
        server.interrupt_acknowledged = False
        server.native_completion_status = None
        server.request = Mock(side_effect=lambda *args, **kwargs: (
            server.messages.put({"method": "turn/completed", "params": {
                "turn": {"id": "turn-test", "status": "interrupted"}}}) or
            {"result": {}}))
        cancelled = threading.Event()
        cancelled.set()
        self.assertEqual(server.wait_turn("turn-test", 1, cancelled),
                         ("cancelled", "cancelled_by_user"))
        self.assertTrue(server.interrupt_acknowledged)
        self.assertEqual(server.native_completion_status, "interrupted")


if __name__ == "__main__":
    unittest.main()
