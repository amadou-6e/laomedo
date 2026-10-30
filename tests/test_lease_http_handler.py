"""Real loopback wire controls with internal collaborators, not agent acceptance."""

from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import io
import json
import threading
import unittest
from unittest.mock import patch

from laomedo.host.leases.handler import LeaseRequestHandler
from laomedo.host.leases.server import LeaseHTTPServer
from laomedo.host.mediation.errors import MediationError


class RecordingGrantBook:
    """Observe handler forwarding without real credentials or external effects."""

    def __init__(self):
        """Keep only disposable internal authorization observations."""
        self.calls = []

    def check(self, token):
        """Return the existing two-value book interface for an internal token."""
        self.calls.append(token)
        return token == "approved", None


class RecordingMediator:
    """Observe HTTP forwarding and existing exception-to-wire categories."""

    def __init__(self):
        """Initialize task-local observations without services or credentials."""
        self.calls = []
        self.error = None

    def invoke(self, **arguments):
        """Return a small ordered Unicode value or the selected internal failure."""
        self.calls.append(arguments)
        if self.error is not None:
            raise self.error
        return {"nested": {"unicode": "\u00e9"}, "accepted": True}


class LeaseHTTPHandlerTests(unittest.TestCase):
    """Use actual ephemeral TCP listeners and independently fixed wire bytes."""

    def _server(self, book=None, mediator=None, transport=None, instance=None):
        """Start one owned loopback listener and register deterministic cleanup."""
        server = LeaseHTTPServer(book, mediator, transport, instance)
        thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        thread.start()
        self.addCleanup(self._close, server, thread)
        return server

    def _close(self, server, thread):
        """Close only this listener and verify its serving thread exits."""
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        self.assertFalse(thread.is_alive(), "Owned loopback serving thread leaked")

    def _request(self, server, method, path, body=b"", headers=None):
        """Send exact chosen headers, including deliberately missing lengths."""
        connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        try:
            connection.putrequest(method, path)
            for key, value in (headers or {}).items():
                connection.putheader(key, value)
            connection.endheaders(body)
            response = connection.getresponse()
            raw = response.read()
            self.assertEqual(response.getheader("Content-Type"), "application/json")
            self.assertEqual(response.getheader("Content-Length"), str(len(raw)))
            return response.status, raw
        finally:
            connection.close()

    def _post(self, server, body, *, headers=None, path="/v1/mediate"):
        """Use the existing valid prefix while allowing explicit invalid overrides."""
        supplied = {
            "Authorization": "Bearer internal",
            "Content-Length": str(len(body)),
        }
        supplied.update(headers or {})
        return self._request(server, "POST", path, body, supplied)

    def test_dependencies_exist_before_framework_initialization(self):
        """Server construction never binds before its handler dependencies exist."""
        book, mediator, transport = RecordingGrantBook(), RecordingMediator(), object()
        with patch.object(ThreadingHTTPServer, "__init__", autospec=True) as initialize:
            initialize.side_effect = self._observe_initialization
            self.expected = (book, mediator, transport, "instance")
            server = LeaseHTTPServer(book, mediator, transport, "instance")
        initialize.assert_called_once_with(
            server, ("127.0.0.1", 0), LeaseRequestHandler
        )

    def _observe_initialization(self, server, address, handler):
        """Inspect the state at the framework boundary without opening a socket."""
        self.assertEqual(
            (server.book, server.mediator, server.transport, server.instance),
            self.expected,
        )

    def test_health_requires_all_existing_non_none_dependencies(self):
        """Keep readiness's None checks, including an admitted empty instance."""
        mediator, transport = RecordingMediator(), object()
        for selected, expected in (
            ((None, transport, "instance"), (404, b'{"error": "not_found"}')),
            ((mediator, None, "instance"), (404, b'{"error": "not_found"}')),
            ((mediator, transport, None), (404, b'{"error": "not_found"}')),
            ((mediator, transport, ""), (200, b'{"status": "ready", "instance": ""}')),
        ):
            with self.subTest(instance=selected[2], available=selected[0] is not None):
                server = self._server(
                    mediator=selected[0], transport=selected[1], instance=selected[2]
                )
                self.assertEqual(self._request(server, "GET", "/v1/health"), expected)
                self.assertEqual(
                    self._request(server, "GET", "/unknown"),
                    (404, b'{"error": "not_found"}'),
                )

    def test_lease_write_path_and_mediator_precedence_are_unchanged(self):
        """The lease book is called only for the exact original write predicate."""
        book = RecordingGrantBook()
        server = self._server(book=book)
        for path, authorization, status, accepted in (
            ("/write", "Bearer approved", 200, True),
            ("/write", "Bearer refused", 403, False),
            ("/write", "bearer approved", 403, False),
            ("/unknown", "Bearer approved", 403, False),
        ):
            with self.subTest(path=path, authorization=authorization):
                self.assertEqual(
                    self._request(
                        server, "POST", path, headers={"Authorization": authorization}
                    ),
                    (
                        status,
                        b'{"accepted": true}' if accepted else b'{"accepted": false}',
                    ),
                )
        self.assertEqual(book.calls, ["approved", "refused"])
        self.assertEqual(
            self._post(server, b"not-json"), (503, b'{"error": "mediator_unavailable"}')
        )
        mediated = self._server(
            book=book, mediator=RecordingMediator(), transport=object()
        )
        self.assertEqual(
            self._post(
                mediated,
                b"",
                path="/write",
                headers={"Authorization": "Bearer approved"},
            ),
            (403, b'{"accepted": false}'),
        )
        self.assertEqual(book.calls, ["approved", "refused"])

    def test_instance_refusal_precedes_bad_body_and_authorization(self):
        """Keep the original early instance error and avoid invoking the mediator."""
        mediator = RecordingMediator()
        server = self._server(
            mediator=mediator, transport=object(), instance="instance"
        )
        self.assertEqual(
            self._post(
                server,
                b"bad-json",
                headers={
                    "Content-Length": "invalid",
                    "Authorization": "Basic internal",
                },
            ),
            (403, b'{"error": "mediator_instance_mismatch"}'),
        )
        self.assertEqual(mediator.calls, [])

    def test_length_prefix_json_and_exception_categories_are_preserved(self):
        """Reject malformed input before effects and redact caught exception text."""
        mediator = RecordingMediator()
        server = self._server(mediator=mediator, transport=object())
        for length in (None, "invalid", "0", "-1", str(1024 * 1024 + 1)):
            with self.subTest(length=length):
                headers = {"Authorization": "Bearer internal"}
                if length is not None:
                    headers["Content-Length"] = length
                self.assertEqual(
                    self._request(server, "POST", "/v1/mediate", headers=headers),
                    (403, b'{"error": "request_invalid"}'),
                )
        for value in (b"not-json", b"[]", b"null"):
            self.assertEqual(
                self._post(server, value), (403, b'{"error": "request_invalid"}')
            )
        self.assertEqual(
            self._post(server, b"{}", headers={"Authorization": "Basic internal"}),
            (403, b'{"error": "request_invalid"}'),
        )
        self.assertEqual(mediator.calls, [])
        for failure, expected in (
            (MediationError("grant_invalid"), b'{"error": "grant_invalid"}'),
            (ValueError("internal-private-detail"), b'{"error": "request_invalid"}'),
            (TypeError("internal-private-detail"), b'{"error": "request_invalid"}'),
        ):
            mediator.error = failure
            self.assertEqual(self._post(server, b"{}"), (403, expected))

    def test_maximum_body_exact_forwarding_bytes_and_log_suppression(self):
        """Keep the inclusive body limit, optional fields and default ASCII JSON."""
        mediator, transport = RecordingMediator(), object()
        server = self._server(mediator=mediator, transport=transport)
        body = json.dumps(
            {
                "repository": "example/disposable",
                "operation": "git_fetch",
                "payload": {"branch": "main"},
                "effect_id": "effect",
            }
        ).encode()
        body += b" " * (1024 * 1024 - len(body))
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            self.assertEqual(
                self._post(server, body),
                (200, b'{"nested": {"unicode": "\\u00e9"}, "accepted": true}'),
            )
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(
            mediator.calls,
            [
                {
                    "token": "internal",
                    "repository": "example/disposable",
                    "operation": "git_fetch",
                    "payload": {"branch": "main"},
                    "effect_id": "effect",
                    "transport": transport,
                }
            ],
        )
        self.assertEqual(
            self._post(server, b"{}", headers={"Authorization": "Bearer "}),
            (200, b'{"nested": {"unicode": "\\u00e9"}, "accepted": true}'),
        )
        self.assertEqual(
            mediator.calls[-1],
            {
                "token": "",
                "repository": None,
                "operation": None,
                "payload": None,
                "effect_id": None,
                "transport": transport,
            },
        )


if __name__ == "__main__":
    unittest.main()
