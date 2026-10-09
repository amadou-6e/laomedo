"""Credential-free checks for the pre-thread response hold."""

import threading
import unittest
from unittest import mock

try:
    from experiments.exp22 import phase_f_prethread
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    phase_f_prethread = None


@unittest.skipUnless(phase_f_prethread is not None,
                     "experiment source is not installed in the wheel")
class PhaseFHoldTests(unittest.TestCase):
    def test_prepared_async_ack_waits_until_released(self):
        replies = []

        class Handler:
            def _reply(self, code, value):
                replies.append((code, value))

        server = mock.Mock(RequestHandlerClass=Handler)
        release = threading.Event()
        waiting = phase_f_prethread._hold_async_ack(server, mock.Mock(), release)
        handler = object.__new__(server.RequestHandlerClass)
        handler.command = "POST"
        handler.path = "/v1/runs/async"
        worker = threading.Thread(target=handler._reply,
                                  args=(202, {"status": "prepared", "run_id": "run-a"}))
        worker.start()
        self.assertTrue(waiting.wait(timeout=1))
        self.assertEqual(replies, [])
        release.set()
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(replies), 1)

    def test_other_routes_are_not_held(self):
        replies = []

        class Handler:
            def _reply(self, code, value):
                replies.append(code)

        server = mock.Mock(RequestHandlerClass=Handler)
        waiting = phase_f_prethread._hold_async_ack(server, mock.Mock(), threading.Event())
        handler = object.__new__(server.RequestHandlerClass)
        handler.command = "POST"
        handler.path = "/v1/runs/run-a/cancel"
        handler._reply(200, {"status": "cancelled"})
        self.assertFalse(waiting.is_set())
        self.assertEqual(replies, [200])


if __name__ == "__main__":
    unittest.main()
