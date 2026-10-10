"""Task command ownership controls; never touches Windows Task Scheduler."""
from pathlib import Path
from unittest.mock import patch
import unittest
from experiments.exp104 import native_managed_tasks as tasks


class NativeManagedTasksTests(unittest.TestCase):
    def test_cleanup_checks_exact_action_before_unregister(self):
        config = Path("C:/private/S12/host-services.json")
        saved = {"host-services": {"name": "Laomedo-S-1-test-host-services",
                                  "configuration": config, "python": Path("C:/private/python.exe")}}
        commands = []
        with patch.object(tasks, "powershell", side_effect=lambda command: commands.append(command)), \
                patch.object(tasks, "processes", return_value=[]):
            assert tasks.cleanup(saved) == {"host-services": True}
        command = commands[0]
        for marker in ("Actions.Execute -ne", "Actions.Arguments -ne", "Actions.WorkingDirectory -ne",
                       "@($t.Actions).Count -ne 1", "task_ownership_changed"):
            assert marker in command
        assert command.index("task_ownership_changed") < command.index("Unregister-ScheduledTask")
        assert "Remove-Item" not in command
        assert "-TaskName 'Laomedo-S-1-test-host-services'" in command


    def test_cleanup_never_reports_permission_or_ownership_failure_as_success(self):
        saved = {"host-services": {"name": "exact", "configuration": Path("C:/private/config.json"),
                                  "python": Path("C:/private/python.exe")}}
        with patch.object(tasks, "powershell", side_effect=RuntimeError("ownership_changed")), \
                patch.object(tasks, "processes") as processes:
            assert tasks.cleanup(saved) == {"host-services": False}
            processes.assert_not_called()


    def test_unknown_services_and_unsafe_paths_are_refused(self):
        with self.assertRaises(ValueError):
            tasks.expected_arguments("not-a-service", "config")
        with self.assertRaises(ValueError):
            tasks.expected_arguments("host-services", 'config"\nunsafe')
