"""Controller isolation retains listeners while tolerating proc disappearance races."""

import io
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, MagicMock, patch

from laomedo.agents.agents.codex.split.executor import CodexCommandExecutor


class ControllerSocketInspectionTests(TestCase):
    def probe(self):
        executor = object.__new__(CodexCommandExecutor)
        executor._exec = Mock(return_value="")
        executor._controller_listeners(SimpleNamespace(identity="owned"))
        return executor._exec.call_args.args[1][2]

    def test_disappearing_process_and_descriptor_do_not_hide_live_socket(self):
        processes = MagicMock()
        processes.__enter__.return_value = [
            SimpleNamespace(name="123", path="active"),
            SimpleNamespace(name="456", path="exited"),
        ]
        listing = MagicMock()
        listing.__enter__.return_value = [
            SimpleNamespace(path="live"),
            SimpleNamespace(path="gone"),
        ]
        output = io.StringIO()
        with (
            patch("os.scandir", side_effect=[processes, listing, FileNotFoundError()]),
            patch("os.readlink", side_effect=["socket:[42]", FileNotFoundError()]),
            redirect_stdout(output),
        ):
            exec(self.probe(), {})
        self.assertEqual(output.getvalue(), "socket:[42]\n")

    def test_permission_failure_is_not_treated_as_process_exit(self):
        with (
            patch("os.scandir", side_effect=PermissionError()),
            self.assertRaises(PermissionError),
        ):
            exec(self.probe(), {})

    def test_owned_tcp_listener_still_refuses_isolation(self):
        executor = object.__new__(CodexCommandExecutor)
        executor._exec = Mock(
            side_effect=[
                "socket:[42]",
                "header\n0: local remote 0A x x x x x 42",
                "header",
                "header",
                "header",
                "header",
            ]
        )
        self.assertEqual(
            executor._controller_listeners(SimpleNamespace(identity="owned")), {"tcp"}
        )
