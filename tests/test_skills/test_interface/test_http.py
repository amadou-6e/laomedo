"""Internal socket controls with disposable collaborators; not UI acceptance."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener

from laomedo.http.redirect import NoRedirect
from laomedo.skills.interface.sources.server import SkillSourceServer
from laomedo.skills.sources.errors import SourceError
from support.http_server import RunningHTTPServer
from test_skills.test_interface.utils import http_cases


class SkillHTTPTests(unittest.TestCase):
    """Protect actual listener admission and exact safe response projections."""

    def _start(self, server):
        lifetime = RunningHTTPServer(server)
        self.addCleanup(lifetime.__exit__, None, None, None)
        lifetime.__enter__()
        return f"http://127.0.0.1:{server.server_port}"

    def _post(self, base, route, token, body):
        request = Request(
            base + route,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
        )
        try:
            response = build_opener(NoRedirect()).open(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.code, json.loads(response.read()), response.headers

    def test_tokens_and_service_bindings_are_instance_local(self):
        for case in http_cases():
            with self.subTest(route=case.route):
                services = [MagicMock(), MagicMock()]
                tokens = ["internal-one-" + "a" * 32, "internal-two-" + "b" * 32]
                for index, service in enumerate(services):
                    getattr(service, case.method).return_value = {"instance": index}
                bases = [
                    self._start(case.server_type(service, token, port=0))
                    for service, token in zip(services, tokens)
                ]
                for index, base in enumerate(bases):
                    refused = self._post(base, case.route, tokens[1 - index], case.body)
                    self.assertEqual(
                        refused[:2], (401, {"error_category": "unauthorized"})
                    )
                    getattr(services[index], case.method).assert_not_called()
                    accepted = self._post(base, case.route, tokens[index], case.body)
                    self.assertEqual(accepted[:2], (200, {"instance": index}))
                    self.assertEqual(accepted[2]["Cache-Control"], "no-store")
                    self.assertNotIn(tokens[index], json.dumps(accepted[1]))

    def test_unknown_domain_failures_use_safe_transport_categories(self):
        for case in http_cases():
            with self.subTest(route=case.route):
                service = MagicMock()
                getattr(service, case.method).side_effect = RuntimeError(
                    "private-payload private-token /private/path"
                )
                token = "internal-control-" + "x" * 32
                base = self._start(case.server_type(service, token, port=0))
                status, result, _ = self._post(base, case.route, token, case.body)
                self.assertEqual(
                    (status, result), (400, {"error_category": case.fallback})
                )
                self.assertNotIn("private", json.dumps(result))
                getattr(service, case.method).assert_called_once()

    def test_source_domain_codes_are_preserved(self):
        service = MagicMock()
        service.discover.side_effect = SourceError("local_source_not_allowed")
        token = "internal-control-" + "s" * 32
        base = self._start(SkillSourceServer(service, token, port=0))
        status, result, _ = self._post(
            base, "/v1/skill-sources/discover", token, {"source": "source"}
        )
        self.assertEqual(
            (status, result), (400, {"error_category": "local_source_not_allowed"})
        )

    def test_clients_keep_supported_safe_error_projections(self):
        for case in http_cases():
            with self.subTest(route=case.route):
                service = MagicMock()
                getattr(service, case.method).side_effect = (
                    SourceError("local_source_not_allowed")
                    if case.method == "discover"
                    else RuntimeError("private-detail")
                )
                token = "internal-client-" + "k" * 32
                base = self._start(case.server_type(service, token, port=0))
                with tempfile.TemporaryDirectory() as temporary:
                    token_file = Path(temporary) / "client-token"
                    token_file.write_text(token, encoding="utf-8")
                    with patch.dict(
                        os.environ,
                        {
                            case.prefix + "_URL": base,
                            case.prefix + "_TOKEN_FILE": str(token_file),
                        },
                    ):
                        with self.assertRaisesRegex(
                            ValueError, "^" + case.client_error + "$"
                        ):
                            case.client(case.method, **case.body)
