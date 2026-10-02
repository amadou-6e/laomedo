"""Credential-free command recipe and MCP capability checks."""

from pathlib import Path
import json
import tempfile
import unittest
from urllib import error, request

from laomedo.opencode_boundary import CommandBroker, worker_command


class BoundaryTests(unittest.TestCase):
    def test_worker_never_mounts_controller_profile_or_environment(self):
        args = worker_command("owned", Path("workspace"), Path("canonical"), Path("store"), "pwd")
        self.assertNotIn("-e", args)
        self.assertNotIn("--privileged", args)
        self.assertIn("ALL", args)
        mounts = [args[index + 1] for index, value in enumerate(args) if value == "--mount"]
        self.assertEqual(len(mounts), 3)
        self.assertTrue(any("target=/canonical,readonly" in value for value in mounts))
        self.assertTrue(any("target=/store,readonly" in value for value in mounts))
        self.assertFalse(any("auth" in value or "profile" in value for value in mounts))

    def test_mcp_requires_bearer_capability_and_rejects_unknown_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            broker = CommandBroker(path, path, path, path)
            self.addCleanup(broker.close)
            url = "http://127.0.0.1:" + str(broker.server.server_port) + "/mcp"
            payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode()
            with self.assertRaises(error.HTTPError) as failure:
                request.urlopen(request.Request(url, data=payload))
            self.assertEqual(failure.exception.code, 403)
            headers = {"Authorization": "Bearer " + broker.token, "Content-Type": "application/json"}
            with request.urlopen(request.Request(url, data=payload, headers=headers)) as response:
                body = json.load(response)
            self.assertEqual(body["result"]["tools"][0]["name"], "exec")
            with self.assertRaisesRegex(ValueError, "unknown_worker_tool"):
                broker.rpc("tools/call", {"name": "read_personal_profile"})


if __name__ == "__main__":
    unittest.main()
