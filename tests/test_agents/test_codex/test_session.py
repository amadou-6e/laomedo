"""Native session thread ownership across independently admitted requests."""

import asyncio
import threading
import unittest

from laomedo.agents.agents.codex.session import CodexSessionOwner
from laomedo.agents.errors import RunnerError


class CodexSessionOwnerTests(unittest.TestCase):
    def test_successive_requests_use_one_running_loop_and_transport_thread(self):
        owner = CodexSessionOwner()
        try:
            first = owner.run(self.identity())
            marker = threading.Event()
            owner.run(self.schedule_marker(marker))
            self.assertTrue(
                marker.wait(2), "native readers must remain live between requests"
            )
            second = owner.run(self.identity())
            self.assertEqual(first, second)
            self.assertNotEqual(first[0], threading.get_ident())
        finally:
            owner.close()
        self.assertFalse(owner._thread.is_alive())

    def test_closed_owner_refuses_work_without_leaving_an_unawaited_coroutine(self):
        owner = CodexSessionOwner()
        owner.close()
        owner.close()
        operation = self.identity()
        with self.assertRaisesRegex(RunnerError, "runner_transport_failed"):
            owner.run(operation)
        self.assertIsNone(operation.cr_frame)

    @staticmethod
    async def identity():
        return threading.get_ident(), id(asyncio.get_running_loop())

    @staticmethod
    async def schedule_marker(marker):
        asyncio.get_running_loop().call_later(0.01, marker.set)
