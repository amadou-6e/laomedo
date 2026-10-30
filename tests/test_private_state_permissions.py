"""Internal legacy-permission and strict-path controls; no credentials or Docker."""

import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import call, patch

from laomedo.host.credentials.siwc.errors import AuthError
from laomedo.host.credentials.siwc.utils import _restrict_windows_directory
from laomedo.host.private_state.errors import PrivateStateError
from laomedo.host.private_state.models import DirectoryPermissionPolicy
from laomedo.host.private_state.utils import prepare_private_directory
from laomedo.host.private_state.utils import restrict_directory
from laomedo.host.private_state.utils import validate_private_path


class LegacyDirectoryPermissionTests(unittest.TestCase):
    def test_windows_arguments_and_kwargs_remain_unchanged(self):
        path = Path("private-leaf")
        with (
            patch("laomedo.host.private_state.utils.os.name", "nt"),
            patch(
                "laomedo.host.private_state.utils.subprocess.run",
                side_effect=[
                    SimpleNamespace(returncode=0, stdout='"user","S-1-5-21-123"'),
                    SimpleNamespace(returncode=0),
                ],
            ) as run,
        ):
            self.assertIsNone(_restrict_windows_directory(path))
        self.assertEqual(
            run.call_args_list,
            [
                call(
                    ["whoami", "/user", "/fo", "csv", "/nh"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                ),
                call(
                    [
                        "icacls",
                        str(path),
                        "/inheritance:r",
                        "/grant:r",
                        "*S-1-5-21-123:(OI)(CI)F",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                ),
            ],
        )

    def test_legacy_policy_failure_translates_without_native_details(self):
        path = Path("private-leaf")
        for identity in (
            SimpleNamespace(returncode=1, stdout="private-native-output"),
            SimpleNamespace(returncode=0, stdout="malformed"),
            SimpleNamespace(returncode=0, stdout='"user","not-a-sid"'),
        ):
            with (
                self.subTest(status=identity.returncode),
                patch("laomedo.host.private_state.utils.os.name", "nt"),
                patch(
                    "laomedo.host.private_state.utils.subprocess.run",
                    return_value=identity,
                ),
                self.assertRaises(AuthError) as raised,
            ):
                _restrict_windows_directory(path)
            self.assertEqual(str(raised.exception), "auth_store_permissions_unverified")
            self.assertTrue(raised.exception.__suppress_context__)

    def test_legacy_native_failures_are_not_reclassified(self):
        path = Path("private-leaf")
        for error in (OSError("private"), subprocess.TimeoutExpired("whoami", 10)):
            with (
                self.subTest(kind=type(error).__name__),
                patch("laomedo.host.private_state.utils.os.name", "nt"),
                patch(
                    "laomedo.host.private_state.utils.subprocess.run", side_effect=error
                ),
                self.assertRaises(type(error)) as raised,
            ):
                _restrict_windows_directory(path)
            self.assertIs(raised.exception, error)

    def test_posix_legacy_chmod_is_not_replaced_by_strict_admission(self):
        path = Path("relative-is-legacy-valid")
        with (
            patch("laomedo.host.private_state.utils.os.name", "posix"),
            patch("laomedo.host.private_state.utils.os.chmod") as chmod,
        ):
            result = restrict_directory(path)
        chmod.assert_called_once_with(path, 0o700)
        self.assertIsNone(result.owner_sid)


class StrictPrivateDirectoryTests(unittest.TestCase):
    def test_relative_and_checkout_paths_are_rejected_before_creation(self):
        with self.assertRaisesRegex(PrivateStateError, "private_state_path_unverified"):
            validate_private_path(Path("relative"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.joinpath(".git").write_text("gitdir: elsewhere", encoding="utf-8")
            leaf = root / "not-created" / "leaf"
            with self.assertRaisesRegex(
                PrivateStateError, "private_state_inside_checkout"
            ):
                prepare_private_directory(leaf)
            self.assertFalse(leaf.exists())

    def test_file_ancestor_and_lexical_traversal_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "file"
            file.touch()
            with self.assertRaises((PrivateStateError, NotADirectoryError)):
                validate_private_path(file / "leaf")
            with self.assertRaisesRegex(
                PrivateStateError, "private_state_path_unverified"
            ):
                validate_private_path(root / ".." / "leaf")

    @unittest.skipUnless(os.name == "nt", "Windows descriptor adapter")
    def test_existing_directory_is_verified_without_changing_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            policy = DirectoryPermissionPolicy(
                whoami=path / "whoami.exe",
                icacls=path / "icacls.exe",
                environment={},
                deadline=100.0,
            )
            with (
                patch(
                    "laomedo.host.private_state.utils._owner_sid",
                    return_value="S-1-5-21-123",
                ),
                patch(
                    "laomedo.host.private_state.utils.restrict_directory"
                ) as restrict,
                patch(
                    "laomedo.host.private_state.utils.WindowsDirectorySecurity"
                ) as security,
            ):
                prepare_private_directory(path, policy=policy)
            restrict.assert_not_called()
            security.return_value.verify.assert_called_once_with(path, "S-1-5-21-123")
            security.return_value.restrict.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows descriptor adapter")
    def test_new_leaf_uses_native_owner_only_policy_not_legacy_icacls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private"
            policy = DirectoryPermissionPolicy(
                whoami=path / "whoami.exe",
                icacls=path / "icacls.exe",
                environment={},
                deadline=100000000000.0,
            )
            with (
                patch(
                    "laomedo.host.private_state.utils._owner_sid",
                    return_value="S-1-5-21-123",
                ),
                patch("laomedo.host.private_state.utils.restrict_directory") as legacy,
                patch(
                    "laomedo.host.private_state.utils.WindowsDirectorySecurity"
                ) as security,
            ):
                prepare_private_directory(path, policy=policy)
            legacy.assert_not_called()
            self.assertEqual(
                security.return_value.method_calls,
                [
                    call.restrict(path, "S-1-5-21-123"),
                    call.verify(path, "S-1-5-21-123"),
                ],
            )

    def test_policy_deadline_is_fixed_and_values_are_not_dumped(self):
        path = Path.cwd()
        policy = DirectoryPermissionPolicy(
            whoami=path / "whoami.exe",
            icacls=path / "icacls.exe",
            environment={"PATH": "private"},
            deadline=100.0,
        )
        self.assertEqual(policy.timeout_seconds(20, 90), 10)
        self.assertEqual(policy.timeout_seconds(20, 99), 1)
        with self.assertRaisesRegex(
            PrivateStateError, "private_state_deadline_exceeded"
        ):
            policy.timeout_seconds(20, 100)
        self.assertEqual(policy.model_dump(), {})
        self.assertNotIn("private", repr(policy))


if __name__ == "__main__":
    unittest.main()
