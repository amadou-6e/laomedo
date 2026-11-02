"""Internal HTTP controls only; no live provider or acceptance evidence."""

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from laomedo.work_graph.client import LangflowLocalClient
from laomedo.work_graph.runs.errors import LaunchError


def response(value):
    return io.BytesIO(json.dumps(value).encode())


class LocalGraphAuthTests(unittest.TestCase):
    def test_expired_local_token_refreshes_only_the_read(self):
        expired = HTTPError("http://127.0.0.1/flow", 401, "expired", {}, None)
        with patch(
            "laomedo.work_graph.client.request.urlopen",
            side_effect=[
                response({"access_token": "old"}),
                expired,
                response({"access_token": "new"}),
                response({"id": "flow"}),
            ],
        ) as http:
            client = LangflowLocalClient("http://127.0.0.1:7898")
            self.assertEqual(client.fetch("flow"), {"id": "flow"})
        calls = http.call_args_list
        self.assertEqual(len(calls), 4)
        self.assertTrue(calls[2].args[0].endswith("/api/v1/auto_login"))
        self.assertEqual(calls[1].args[0].get_method(), "GET")
        self.assertEqual(calls[3].args[0].get_method(), "GET")
        self.assertEqual(calls[3].args[0].get_header("Authorization"), "Bearer new")

    def test_repeated_unauthorized_read_is_bounded(self):
        with patch(
            "laomedo.work_graph.client.request.urlopen",
            side_effect=[
                response({"access_token": "old"}),
                HTTPError("local", 401, "expired", {}, None),
                response({"access_token": "new"}),
                HTTPError("local", 401, "refused", {}, None),
            ],
        ) as http:
            client = LangflowLocalClient("http://127.0.0.1:7898")
            with self.assertRaisesRegex(LaunchError, "saved_flow_fetch_failed"):
                client.fetch("flow")
        self.assertEqual(http.call_count, 4)

    def test_forbidden_read_does_not_reauthenticate(self):
        with patch(
            "laomedo.work_graph.client.request.urlopen",
            side_effect=[
                response({"access_token": "old"}),
                HTTPError("local", 403, "forbidden", {}, None),
            ],
        ) as http:
            client = LangflowLocalClient("http://127.0.0.1:7898")
            with self.assertRaisesRegex(LaunchError, "saved_flow_fetch_failed"):
                client.fetch("flow")
        self.assertEqual(http.call_count, 2)
