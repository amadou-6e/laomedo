"""Synthetic credential-source checks; no user token or network is used."""

from pathlib import Path
import tempfile
import unittest

from laomedo.host_token_connection import HostTokenConnection


class HostTokenConnectionTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.path = Path(self.root.name) / "private.env"
        self.path.write_text("OTHER=not-used\nGH=synthetic-first\n", encoding="utf-8")

    def connection(self):
        return HostTokenConnection(
            connection_id="selected", generation=1,
            repository="example/disposable", token_file=self.path)

    def test_exact_selection_and_rotation_fail_closed(self):
        selected = self.connection()
        self.assertTrue(selected.current("selected", 1, "example/disposable"))
        self.assertEqual(selected.token("selected", 1), "synthetic-first")
        self.assertFalse(selected.current("selected", 2, "example/disposable"))
        self.assertFalse(selected.current("selected", 1, "example/other"))
        self.path.write_text("GH=synthetic-second\n", encoding="utf-8")
        self.assertFalse(selected.current("selected", 1, "example/disposable"))
        with self.assertRaises(KeyError):
            selected.token("selected", 1)
        self.path.unlink()
        self.assertFalse(selected.current("selected", 1, "example/disposable"))

    def test_file_inside_agent_mount_or_duplicate_key_is_refused(self):
        with self.assertRaisesRegex(ValueError, "credential_inside_agent_mount"):
            HostTokenConnection(connection_id="selected", generation=1,
                repository="example/disposable", token_file=self.path,
                forbidden_mount=self.root.name)
        self.path.write_text("GH=synthetic-first\nGH=synthetic-second\n",
                             encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "credential_file_unavailable"):
            self.connection()


if __name__ == "__main__":
    unittest.main()
