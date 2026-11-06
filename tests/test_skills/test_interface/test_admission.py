"""Reject unsafe listener configuration before binding any socket."""

from http.server import ThreadingHTTPServer
import unittest
from unittest.mock import patch

from laomedo.skills.interface.operations.server import SkillOperationServer
from laomedo.skills.interface.sources.server import SkillSourceServer


class SkillListenerAdmissionTests(unittest.TestCase):
    def test_bad_tokens_are_refused_before_socket_creation(self):
        for server, code in (
            (SkillSourceServer, "private_source_service_required"),
            (SkillOperationServer, "private_skill_service_required"),
        ):
            tokens = [None, 42, "", "short", "a" * 31]
            if server is SkillOperationServer:
                tokens.append("a" * 513)
            for token in tokens:
                with self.subTest(
                    server=server.__name__, token_type=type(token).__name__
                ):
                    with patch.object(ThreadingHTTPServer, "__init__") as bind:
                        with self.assertRaisesRegex(ValueError, "^" + code + "$"):
                            server(object(), token, port=0)
                        bind.assert_not_called()

    def test_source_bind_address_must_be_the_fixed_loopback_address(self):
        for host in ("0.0.0.0", "192.0.2.1", "localhost", "::1"):
            with (
                self.subTest(host=host),
                patch.object(ThreadingHTTPServer, "__init__") as bind,
            ):
                with self.assertRaisesRegex(
                    ValueError, "^private_source_service_required$"
                ):
                    SkillSourceServer(object(), "a" * 32, host=host, port=0)
                bind.assert_not_called()
