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
