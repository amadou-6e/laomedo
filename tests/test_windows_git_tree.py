"""Actual owned Windows children; internal containment, not live source acceptance."""

import ctypes
from ctypes.wintypes import BOOL, DWORD, HANDLE, LONG, WCHAR
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from laomedo.git.command import GitCommandRunner
from laomedo.git.errors import GitCommandLimitExceeded
from laomedo.git.models import (
    GitCommand,
    GitExecutionBudget,
    GitExecutionContext,
    GitEnvironmentProfile,
)

ROOT = Path(__file__).resolve().parents[1]


class NativeProcessEntry(ctypes.Structure):
    """PROCESSENTRY32W for an independent, read-only descendant snapshot."""

    _fields_ = [
        ("dwSize", DWORD),
        ("cntUsage", DWORD),
        ("th32ProcessID", DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", DWORD),
        ("cntThreads", DWORD),
        ("th32ParentProcessID", DWORD),
        ("pcPriClassBase", LONG),
        ("dwFlags", DWORD),
        ("szExeFile", WCHAR * 260),
    ]


@unittest.skipUnless(os.name == "nt", "Windows Job Object contract")
class WindowsGitTreeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="laomedo-git-job-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def command(self, deadline=None):
        return GitCommand(
            arguments=["--version"],
            cwd=self.root,
            context=GitExecutionContext(
                profile=GitEnvironmentProfile.ISOLATED_HTTPS_READ_ONLY,
                hooks_path=self.root,
                timeout=5.0,
            ),
            budget=GitExecutionBudget(
                stdout_limit=128, operation_deadline=deadline or time.monotonic() + 5
            ),
        )

    def descendants(self, pid):
        """Inspect parent links independently of the job-accounting implementation."""
        native = ctypes.WinDLL("kernel32", use_last_error=True)
        native.CreateToolhelp32Snapshot.argtypes = [DWORD, DWORD]
        native.CreateToolhelp32Snapshot.restype = HANDLE
        native.Process32FirstW.argtypes = [HANDLE, ctypes.POINTER(NativeProcessEntry)]
        native.Process32FirstW.restype = BOOL
        native.Process32NextW.argtypes = [HANDLE, ctypes.POINTER(NativeProcessEntry)]
        native.Process32NextW.restype = BOOL
        native.CloseHandle.argtypes = [HANDLE]
        native.CloseHandle.restype = BOOL
        snapshot = native.CreateToolhelp32Snapshot(2, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            entry = NativeProcessEntry()
            entry.dwSize = ctypes.sizeof(entry)
            parents = {}
            available = native.Process32FirstW(snapshot, ctypes.byref(entry))
            while available:
                parents[entry.th32ProcessID] = entry.th32ParentProcessID
                entry.dwSize = ctypes.sizeof(entry)
                available = native.Process32NextW(snapshot, ctypes.byref(entry))
            self.assertEqual(ctypes.get_last_error(), 18)
        finally:
            native.CloseHandle(snapshot)
        owned = {pid}
        while True:
            expanded = owned | {
                child for child, parent in parents.items() if parent in owned
            }
            if expanded == owned:
                return owned - {pid}
            owned = expanded

    def test_job_accounts_for_all_descendants_after_active_limit_and_root_success(self):
        import _winapi
        from laomedo.git.windows.tree import WindowsProcessTree

        original_launch = subprocess.Popen
        original_terminate = WindowsProcessTree.terminate
        for mode in ("descendant", "orphan"):
            marker = self.root / (mode + ".json")
            roots, handles, counts = [], [], []
            runner = GitCommandRunner()
            original_start = runner._start_process

            def launch(arguments, **options):
                self.assertEqual(
                    options["creationflags"], subprocess.CREATE_NEW_PROCESS_GROUP | 4
                )
                process = original_launch(
                    [
                        sys.executable,
                        str(ROOT / "tests/git_process_control.py"),
                        mode,
                        str(marker),
                    ],
                    **options,
                )
                roots.append(process)
                return process

            def started(*args, **kwargs):
                process = original_start(*args, **kwargs)
                until = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < until:
                    time.sleep(0.01)
                self.assertTrue(marker.exists(), "The owned child did not start")
                child = json.loads(marker.read_text(encoding="utf-8"))
                handle = _winapi.OpenProcess(0x100000 | 0x1000, False, child["pid"])
                handles.append(handle)
                self.assertEqual(
                    _winapi.WaitForSingleObject(handle, 0), _winapi.WAIT_TIMEOUT
                )
                if mode == "orphan":
                    process.wait(timeout=5)
                return process

            def terminated(tree, deadline):
                before = tree.active_processes()
                result = original_terminate(tree, deadline)
                counts.append((before, tree.active_processes(), result))
                return result

            try:
                with (
                    self.subTest(mode=mode),
                    patch("subprocess.Popen", new=launch),
                    patch.object(runner, "_start_process", side_effect=started),
                    patch.object(WindowsProcessTree, "terminate", new=terminated),
                    patch(
                        "laomedo.git.command.subprocess.run",
                        side_effect=AssertionError(
                            "Budgeted Windows reads must not call taskkill"
                        ),
                    ),
                ):
                    if mode == "descendant":
                        with self.assertRaises(GitCommandLimitExceeded) as raised:
                            runner.run(self.command(time.monotonic() + 0.8))
                        self.assertTrue(raised.exception.cleanup_verified)
                    else:
                        result = runner.run(self.command())
                        self.assertEqual(result.returncode, 0)
                self.assertTrue(counts)
                self.assertGreater(
                    counts[0][0], 0, "This control must observe live descendants"
                )
                self.assertEqual(counts[-1][1:], (0, True))
                for handle in handles:
                    self.assertEqual(
                        _winapi.WaitForSingleObject(handle, 1000), _winapi.WAIT_OBJECT_0
                    )
                self.assertTrue(all(process.poll() is not None for process in roots))
            finally:
                for handle in handles:
                    _winapi.CloseHandle(handle)
                for process in roots:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)

    def test_failed_assignment_never_executes_the_suspended_root(self):
        from laomedo.git.windows.tree import WindowsProcessTree

        original = subprocess.Popen
        processes = []

        def launch(arguments, **options):
            process = original(
                [
                    sys.executable,
                    str(ROOT / "tests/git_process_control.py"),
                    "emit",
                    "32",
                    "0",
                ],
                **options,
            )
            processes.append(process)
            return process

        with (
            patch("subprocess.Popen", new=launch),
            patch.object(
                WindowsProcessTree,
                "attach",
                side_effect=PermissionError("internal assignment refusal"),
            ),
            patch.object(WindowsProcessTree, "resume") as resume,
            self.assertRaises(PermissionError),
        ):
            GitCommandRunner().run(self.command())
        resume.assert_not_called()
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].poll())

    def test_nested_job_admission_and_termination_leave_other_owned_process_untouched(
        self,
    ):
        from laomedo.git.windows.tree import WindowsProcessTree

        base = Path(sys._base_executable).resolve(strict=True)
        self.assertTrue(base.is_file())
        probe = subprocess.run(
            [
                str(base),
                "-I",
                "-S",
                "-c",
                "import json,sys; print(json.dumps([sys.executable,sys.prefix,sys.base_prefix]))",
            ],
            capture_output=True,
            check=True,
            timeout=5,
        )
        executable, prefix, base_prefix = json.loads(probe.stdout)
        self.assertEqual(Path(executable).resolve(strict=True), base)
        self.assertEqual(
            prefix, base_prefix, "The control must use a direct base interpreter"
        )
        outer, inner = WindowsProcessTree(), WindowsProcessTree()
        root = None
        unrelated = subprocess.Popen(
            [
                str(base),
                "-I",
                "-S",
                str(ROOT / "tests/git_process_control.py"),
                "wait",
                "30",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            self.assertEqual(self.descendants(unrelated.pid), set())
            root = subprocess.Popen(
                [
                    sys.executable,
                    str(ROOT / "tests/git_process_control.py"),
                    "wait",
                    "30",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | 4,
            )
            outer.attach(root)
            inner.attach(root)
            inner.resume(root.pid)
            self.assertGreater(inner.active_processes(), 0)
            self.assertGreater(outer.active_processes(), 0)
            self.assertTrue(inner.terminate(time.monotonic() + 5))
            root.wait(timeout=5)
            self.assertEqual(inner.active_processes(), 0)
            self.assertEqual(outer.active_processes(), 0)
            self.assertIsNone(unrelated.poll())
            self.assertEqual(self.descendants(unrelated.pid), set())
        finally:
            inner.close()
            outer.close()
            if root is not None and root.poll() is None:
                root.kill()
                root.wait(timeout=5)
            unrelated.kill()
            unrelated.wait(timeout=5)
            self.assertIsNotNone(unrelated.poll())
            self.assertEqual(self.descendants(unrelated.pid), set())
