"""No-network checks of the one-shot EXP-104 probe configuration."""

import unittest
from unittest import mock
import importlib.util
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile


_PROBE = Path(__file__).resolve().parents[1] / "experiments" / "exp104" / "live_probe.py"
_SPEC = importlib.util.spec_from_file_location("exp104_live_probe_config", _PROBE)
live_probe = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(live_probe)


class LiveProbeConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.original_identity = live_probe.IDENTITY
        self.original_connection = live_probe.CONNECTION_ID
        self.addCleanup(live_probe.select_fresh_identity,
                        "exp104-test-reset-0001", "exp104-test-connection")

    def test_fresh_identity_changes_every_effect_namespace(self):
        live_probe.select_fresh_identity("exp104-s4-testunused-01",
                                         "exp104-s4-selected-gh")
        self.assertEqual(live_probe.BRANCH_A, "exp104-s4-testunused-01-a")
        self.assertEqual(live_probe.RUN_B, "exp104-s4-testunused-01-run-b")
        self.assertEqual(live_probe.LEASE_C, "exp104-s4-testunused-01-lease-c")
        self.assertEqual(live_probe.CONTAINER_A,
                         "laomedo-exp104-s4-testunused-01-a")
        self.assertEqual(live_probe.CONNECTION_ID, "exp104-s4-selected-gh")

    def test_invalid_identity_is_rejected_before_run(self):
        with self.assertRaisesRegex(ValueError, "experiment_identity_invalid"):
            live_probe.select_fresh_identity("../old", "exp104-s4-selected-gh")
        self.assertEqual(live_probe.IDENTITY, self.original_identity)

    def test_all_consumed_identities_refused_before_fresh_state(self):
        for identity in sorted(live_probe.CONSUMED_IDENTITIES):
            with self.subTest(identity=identity), self.assertRaisesRegex(
                    ValueError, "experiment_identity_consumed"):
                live_probe.select_fresh_identity(identity,
                                                 "exp104-s4-selected-gh")
            self.assertEqual(live_probe.IDENTITY, self.original_identity)

    def test_scoped_candidate_refuses_without_selected_token_provenance(self):
        live_probe.select_fresh_identity("exp104-s4-testunused-01",
                                         "exp104-s4-selected-gh")
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "untouched-state"
            with self.assertRaisesRegex(RuntimeError,
                                        "scoped_identity_confirmation_required"):
                live_probe.run(state, Path(directory) / "missing-token", "0" * 40,
                               "GH", None)
            self.assertFalse(state.exists())

    def test_direct_run_refuses_consumed_identity_before_state_creation(self):
        saved = live_probe.IDENTITY
        live_probe.IDENTITY = "exp104-s4-20261007-01"
        try:
            with tempfile.TemporaryDirectory() as directory:
                state = Path(directory) / "new-state"
                with self.assertRaisesRegex(RuntimeError,
                                            "experiment_identity_consumed"):
                    live_probe.run(state, Path(directory) / "missing-token",
                                   "0" * 40, "GH_LAOMEDO",
                                   "selected_repository_only")
                self.assertFalse(state.exists())
        finally:
            live_probe.IDENTITY = saved

    def test_dry_run_uses_selected_helper_without_persisting_git_output(self):
        seen = []

        def fake_run(args, **kwargs):
            seen.append({"args": args, "selected_token_present":
                         kwargs["env"].get("LAOMEDO_MEDIATED_GIT_TOKEN") == "secret",
                         "environment": kwargs["env"]})
            return subprocess.CompletedProcess(args, 1, b"[remote rejected] secret",
                                               b"secret")

        result = live_probe._dry_run_preflight(
            "secret", Path("synthetic-checkout"), "a" * 40,
            "exp104-s4-20261007-01-a", run=fake_run)
        self.assertEqual(result, {"exit_code": 1, "category": "remote_rejected"})
        self.assertIn("--dry-run", seen[0]["args"])
        self.assertNotIn("secret", " ".join(seen[0]["args"]))
        self.assertTrue(seen[0]["selected_token_present"])
        self.assertNotIn("LAOMEDO_MEDIATED_GIT_TOKEN",
                         seen[0]["environment"])

    def test_failure_observation_allowlists_private_push_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            mediator = state / "mediator"
            mediator.mkdir()
            (mediator / "push-diagnostics.jsonl").write_text(
                json.dumps({"category": "remote_rejected", "exit_code": 1,
                            "raw_stderr": "synthetic-secret"}) + "\n",
                encoding="utf-8")
            records = live_probe._diagnostic_records(state)
            self.assertEqual(records, [{"category": "remote_rejected",
                                        "exit_code": 1}])
            self.assertNotIn("synthetic-secret", json.dumps(records))

    def test_malformed_diagnostic_does_not_hide_original_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            mediator = state / "mediator"
            mediator.mkdir()
            (mediator / "push-diagnostics.jsonl").write_text(
                '{"category": "remote_rejected"', encoding="utf-8")
            self.assertEqual(live_probe._safe_diagnostic_records(state),
                             {"records": [], "error": "invalid_or_unavailable"})

    def test_non_object_diagnostic_does_not_hide_original_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            mediator = state / "mediator"
            mediator.mkdir()
            (mediator / "push-diagnostics.jsonl").write_text(
                "[]\n", encoding="utf-8")
            self.assertEqual(live_probe._safe_diagnostic_records(state),
                             {"records": [], "error": "invalid_or_unavailable"})

    def test_durable_effect_lookup_is_read_only_and_allowlisted(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            mediator = state / "mediator"
            mediator.mkdir()
            database = mediator / "mediator.sqlite"
            with closing(sqlite3.connect(database)) as db:
                with db:
                    db.execute("CREATE TABLE effects (run_id TEXT, effect_id TEXT, state TEXT)")
                    db.execute("INSERT INTO effects VALUES ('run-a', 'effect-a', 'unknown')")
            self.assertEqual(live_probe._stored_effect_state(
                state, "run-a", "effect-a"), {"state": "unknown", "error": None})
            self.assertEqual(live_probe._stored_effect_state(
                state, "run-b", "effect-a"), {"state": None, "error": None})

    def test_main_preserves_original_failure_with_relative_state_and_bad_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state"
            mediator = state / "mediator"
            mediator.mkdir(parents=True)
            (mediator / "push-diagnostics.jsonl").write_text(
                "[]\n", encoding="utf-8")
            with closing(sqlite3.connect(mediator / "mediator.sqlite")) as db:
                with db:
                    db.execute("CREATE TABLE effects (run_id TEXT, effect_id TEXT, state TEXT)")
                    db.execute("INSERT INTO effects VALUES (?, ?, ?)",
                               ("exp104-s4-testunused-02-run-a",
                                "exp104-s4-testunused-02-push-a", "unknown"))
            record = root / "record.json"
            relative_state = Path(os.path.relpath(state, Path.cwd()))
            argv = ["live_probe.py", "--state", str(relative_state),
                    "--token-file", str(root / "unused-token"),
                    "--code-sha", "0" * 40, "--record", str(record),
                    "--identity", "exp104-s4-testunused-02",
                    "--connection-id", "exp104-s4-selected-gh"]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                    live_probe, "run", side_effect=RuntimeError("synthetic_failure")):
                with self.assertRaisesRegex(RuntimeError, "synthetic_failure"):
                    live_probe.main()
            result = json.loads(record.read_text(encoding="utf-8"))
            self.assertEqual(result["failure_code"], "synthetic_failure")
            self.assertEqual(result["stored_a_push_effect"],
                             {"state": "unknown", "error": None})
            self.assertEqual(result["push_diagnostics"],
                             {"records": [], "error": "invalid_or_unavailable"})

    def test_secret_canary_reports_only_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "safe.txt").write_text("safe", encoding="utf-8")
            (root / "bad.txt").write_text("hidden-test-secret", encoding="utf-8")
            self.assertEqual(live_probe._secret_canary(root, "hidden-test-secret"),
                             {"files_scanned": 2, "exact_token_hits": 1})


if __name__ == "__main__":
    unittest.main()
