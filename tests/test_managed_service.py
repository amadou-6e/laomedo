import json
from pathlib import Path
import tempfile
import unittest

from laomedo.managed_service import configuration_arguments


class ManagedServiceTests(unittest.TestCase):
    def test_explicit_file_reference_not_credential_is_passed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps({"token_file": "host-only.env",
                                       "token_key": "GH_LAOMEDO"}))
            self.assertEqual(configuration_arguments("host-services", path),
                             ["--token-file", "host-only.env", "--token-key", "GH_LAOMEDO"])

    def test_credential_and_unknown_fields_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            for value in ({"token": "synthetic"}, {"command": "evil"},
                          {"state": "bad\npath"}, {"state": True}, []):
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    configuration_arguments("host-services", path)

    def test_verifier_cannot_accept_token_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps({"token_file": "host-only.env"}))
            with self.assertRaises(ValueError):
                configuration_arguments("bundle-verifier", path)
