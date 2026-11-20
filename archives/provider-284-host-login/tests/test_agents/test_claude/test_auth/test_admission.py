"""Internal concurrency/deadline controls; real mirror evidence is separate."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
import time
import unittest
from unittest.mock import patch

from laomedo.agents.agents.claude.auth.errors import LocalClaudeLoginError
from laomedo.agents.agents.claude.auth.settings import MIRROR_LOCK
from laomedo.agents.agents.claude.auth.utils import mirror_login


class LoginAdmissionTests(unittest.TestCase):
    def test_simultaneous_callers_do_not_race_the_owned_receipt(self):
        entered = Event()
        release = Event()
        second_caller = Event()
        second_copy = Event()
        counter = Lock()
        active = 0
        peak = 0
        calls = 0

        def copy(*args, **kwargs):
            nonlocal active, peak, calls
            with counter:
                active += 1
                peak = max(peak, active)
                calls += 1
                first = calls == 1
            try:
                if first:
                    entered.set()
                    self.assertTrue(release.wait(2))
                else:
                    second_copy.set()
            finally:
                with counter:
                    active -= 1

        def second():
            second_caller.set()
            mirror_login("laomedo-claude-profile", "image")

        with patch(
            "laomedo.agents.agents.claude.auth.utils._mirror_login", side_effect=copy
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                first = executor.submit(mirror_login, "laomedo-claude-profile", "image")
                try:
                    self.assertTrue(entered.wait(2))
                    following = executor.submit(second)
                    self.assertTrue(second_caller.wait(2))
                    self.assertFalse(second_copy.wait(0.1))
                finally:
                    release.set()
                first.result(timeout=2)
                following.result(timeout=2)
        self.assertEqual((calls, peak), (2, 1))

    def test_waiting_uses_the_existing_deadline_without_copy_or_retry(self):
        self.assertTrue(MIRROR_LOCK.acquire(timeout=1))
        try:
            with patch("laomedo.agents.agents.claude.auth.utils._mirror_login") as copy:
                with self.assertRaisesRegex(
                    LocalClaudeLoginError, "^claude_local_login_copy_failed$"
                ):
                    mirror_login("profile", "image", deadline=time.monotonic() + 0.01)
                copy.assert_not_called()
        finally:
            MIRROR_LOCK.release()

    def test_release_after_failure_and_preserve_explicit_deadline(self):
        deadline = time.monotonic() + 5
        with patch(
            "laomedo.agents.agents.claude.auth.utils._mirror_login",
            side_effect=[LocalClaudeLoginError("claude_host_login_expired"), None],
        ) as copy:
            with self.assertRaisesRegex(
                LocalClaudeLoginError, "claude_host_login_expired"
            ):
                mirror_login("profile", "image", deadline=deadline)
            mirror_login("profile", "image", deadline=deadline)
        self.assertEqual(copy.call_count, 2)
        self.assertEqual(copy.call_args.kwargs["deadline"], deadline)
