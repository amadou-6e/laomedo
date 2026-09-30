"""Contract checks for issue 120's fail-closed probe logic (stdlib only)."""

import tempfile
import ntpath
import unittest
from pathlib import Path
from unittest.mock import patch

from _shared import (construct_env, credential_gate, fingerprint, reserve_model_turn,
                     restore_workspace_snapshot, select_supported_pair,
                     snapshot_workspace, validate_pair)
from probe_stream_events import stream_evidence
from provision_chatgpt_handoff import provision


class ProbeLogicTests(unittest.TestCase):
    def test_private_windows_environment_resolves_system_drive(self):
        with tempfile.TemporaryDirectory(prefix="laomedo-120-env-") as root:
            state = Path(root)
            env = construct_env(state / "home", state / "codex-home",
                                state, state / "binary")
            self.assertEqual(env["SystemDrive"],
                             ntpath.splitdrive(env["SystemRoot"])[0])
            self.assertTrue(env["SystemDrive"].endswith(":"))

    def test_model_pair_validation_rejects_unknown_and_unsupported(self):
        listing = {"result": {"data": [
            {"id": "wide", "isDefault": True,
             "supportedReasoningEfforts": [{"reasoningEffort": "low"},
                                            {"reasoningEffort": "ultra"}]},
            {"id": "narrow", "supportedReasoningEfforts":
             [{"reasoningEffort": "low"}]},
        ]}}
        model, effort, capabilities = select_supported_pair(listing)
        self.assertEqual((model, effort), ("wide", "low"))
        self.assertEqual(select_supported_pair(
            listing, preferred_model="narrow")[:2], ("narrow", "low"))
        self.assertFalse(validate_pair(capabilities, "missing", "low")["accepted"])
        self.assertFalse(validate_pair(capabilities, "wide", "superultra")["accepted"])
        self.assertFalse(validate_pair(capabilities, "narrow", "ultra")["accepted"])

    def test_started_status_is_not_a_tool_result(self):
        started = {"method": "item/started", "params": {
            "threadId": "thread-1", "turnId": "turn-1",
            "item": {"id": "item-1", "type": "commandExecution",
                     "command": "dir", "status": "inProgress"}}}
        self.assertFalse(stream_evidence([started])["tool_call_and_result_observed"])
        completed = {"method": "item/completed", "params": {
            "threadId": "thread-1", "turnId": "turn-1",
            "item": {"id": "item-1", "type": "commandExecution",
                     "command": "dir", "status": "completed", "exitCode": 0}}}
        self.assertTrue(stream_evidence([started, completed])[
            "tool_call_and_result_observed"])
        empty_result = {**completed, "params": {**completed["params"],
                                                 "item": {**completed["params"]["item"],
                                                          "exitCode": None}}}
        self.assertFalse(stream_evidence([started, empty_result])[
            "tool_call_and_result_observed"])
        other_turn = {**completed, "params": {**completed["params"],
                                              "turnId": "turn-2"}}
        self.assertFalse(stream_evidence([started, other_turn])[
            "tool_call_and_result_observed"])

    def test_credential_gate_allows_private_chatgpt_handoff(self):
        with tempfile.TemporaryDirectory(prefix="laomedo-120-test-") as root:
            state = Path(root)
            codex_home = state / "codex-home"
            codex_home.mkdir()
            personal = state / "personal"
            (personal / ".codex").mkdir(parents=True)
            (personal / ".codex" / "auth.json").write_text("same", encoding="utf-8")
            (codex_home / "auth.json").write_text("same", encoding="utf-8")
            with patch("_shared.Path.home", return_value=personal):
                missing = credential_gate(state / "codex", state, {},
                                          codex_home, state, "api_key")
                copied = credential_gate(state / "codex", state, {},
                                         codex_home, state, "api_key",
                                         "store/laomedo/test")
                with patch("_shared.login_status", return_value={
                    "ok": True, "chatgpt": True, "api_key": False}), \
                     patch("_shared.tcp_reachable", return_value=True):
                    handoff = credential_gate(state / "codex", state, {},
                                              codex_home, state)
            self.assertEqual(missing["reason"], "missing_credential_store_reference")
            self.assertEqual(copied["reason"], "copied_personal_auth_file")
            self.assertTrue(handoff["permitted"])
            self.assertEqual(handoff["credential_mode"], "chatgpt_handoff")

    def test_handoff_is_one_time_and_turn_cap_persists(self):
        with tempfile.TemporaryDirectory(prefix="laomedo-120-test-") as root:
            temp = Path(root)
            source = temp / "synthetic-auth.json"
            source.write_text("synthetic-only", encoding="utf-8")
            state = temp / "private-state"
            state.mkdir()
            self.assertTrue(provision(source, state)["provisioned"])
            self.assertEqual((state / "codex-home" / "auth.json").read_text(
                encoding="utf-8"), "synthetic-only")
            with self.assertRaises(FileExistsError):
                provision(source, state)
            self.assertEqual([reserve_model_turn(state) for _ in range(3)],
                             [1, 2, 3])
            with self.assertRaises(ValueError):
                reserve_model_turn(state)

    def test_missing_snapshot_fails_before_changing_project(self):
        with tempfile.TemporaryDirectory(prefix="laomedo-120-test-") as root:
            state = Path(root)
            project = state / "project"
            project.mkdir()
            (project / "fixture.txt").write_text("original", encoding="utf-8")
            expected = fingerprint(project)
            with self.assertRaises(FileNotFoundError):
                restore_workspace_snapshot(state, project, state / "missing", expected)
            self.assertEqual(fingerprint(project), expected)

    def test_snapshot_restore_removes_drift(self):
        with tempfile.TemporaryDirectory(prefix="laomedo-120-test-") as root:
            state = Path(root)
            project = state / "project"
            project.mkdir()
            (project / "fixture.txt").write_text("original", encoding="utf-8")
            snapshot = state / "snapshot"
            expected = snapshot_workspace(state, project, snapshot)
            (project / "drift.txt").write_text("drift", encoding="utf-8")
            self.assertNotEqual(fingerprint(project), expected)
            self.assertEqual(restore_workspace_snapshot(
                state, project, snapshot, expected), expected)
            self.assertFalse((project / "drift.txt").exists())


if __name__ == "__main__":
    unittest.main()
