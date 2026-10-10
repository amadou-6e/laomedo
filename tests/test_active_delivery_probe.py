import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import Request

path = Path(__file__).resolve().parents[1] / "experiments/exp104/probe_active_delivery.py"
spec = importlib.util.spec_from_file_location("active_delivery_probe", path)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class FakeConnectorTests(unittest.TestCase):
    def test_committed_observation_hash_and_controls(self):
        from hashlib import sha256
        raw = path.with_name("ACTIVE-DELIVERY-OBSERVATION.json").read_bytes()
        self.assertEqual(sha256(raw).hexdigest(), "2c649c2d3d3eb0f178c261d7146b721973a353305c0e9266a8131f7e9c10bef8")
        result = json.loads(raw)
        self.assertEqual(result["source_sha"], "f9705522a2a2804943b4c262c1d9c306f6e3029b")
        self.assertEqual(result["result"], "passed")
        for key in ("cleanup_verified", "stage_cleanup_verified", "agent_cleanup_verified",
                    "completed_freeze_denied", "completed_push_denied", "changed_connection_denied",
                    "revoked_new_write_denied", "provider_count_unchanged_after_controls"):
            self.assertIs(result[key], True)
        self.assertEqual(result["revoked_new_write_error"], "grant_unavailable")

    def test_unknown_is_not_a_specific_refusal(self):
        from unittest.mock import Mock
        store = Mock()
        store.invoke.return_value = {"state": "unknown"}
        self.assertIsNone(probe.refusal_code(store))
        store.invoke.side_effect = probe.MediationError("grant_unavailable")
        self.assertEqual(probe.refusal_code(store), "grant_unavailable")

    def test_live_verifier_cannot_claim_cleanup(self):
        from unittest.mock import Mock
        thread = Mock()
        thread.is_alive.return_value = True
        verified, reports = probe.stage_cleanup(Path("unused"), thread)
        self.assertFalse(verified)
        self.assertEqual(reports, [{"detail": "verifier_still_alive"}])

    def test_absence_without_saved_cleanup_is_not_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            attempt = Path(directory) / "attempt"
            attempt.mkdir()
            (attempt / "container-owner.json").write_text("{}")
            with patch.object(probe, "_inspect", return_value=("absent", None)):
                verified, _ = probe.stage_cleanup(Path(directory), None)
            self.assertFalse(verified)
            (attempt / "verification.json").write_text(json.dumps({"container": {"cleanup_verified": True}}))
            with patch.object(probe, "_inspect", return_value=("absent", None)):
                verified, _ = probe.stage_cleanup(Path(directory), None)
            self.assertTrue(verified)

    def test_owned_orphan_is_reconciled(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "container-owner.json").write_text("{}")
            with patch.object(probe, "_inspect", return_value=("owned", "a" * 64)), \
                 patch.object(probe, "reconcile_orphan", return_value={"cleanup_verified": True, "detail": "removed"}) as reconcile:
                verified, _ = probe.stage_cleanup(Path(directory), None)
            self.assertTrue(verified)
            reconcile.assert_called_once()

    def test_readback_head_is_resolved_not_invented(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = probe.FakeGitHub(Path(directory))
            request = Request("https://api.github.com/repos/example/disposable/pulls",
                data=json.dumps({"title": "fixture", "body": "marker", "base": "main", "head": "run-branch"}).encode(), method="POST")
            with patch.object(probe, "git", return_value="a" * 40) as resolve:
                with fake.open(request, 15) as response:
                    self.assertEqual(json.loads(response.read())["head"]["sha"], "a" * 40)
            resolve.assert_called_once_with(Path(directory), "rev-parse", "refs/heads/run-branch")

    def test_fake_endpoint_cannot_forward_arbitrary_path(self):
        fake = probe.FakeGitHub(Path("unused"))
        with self.assertRaisesRegex(ValueError, "fake_target_invalid"):
            fake.open(Request("https://api.github.com/repos/other/repo/pulls"), 15)
