"""Use real native control graphs against an unavailable counted MCP endpoint."""

import argparse
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import tempfile
from urllib.parse import urlsplit

import requests


class UnavailableServer(BaseHTTPRequestHandler):
    """Count upstream connection attempts without serving an MCP result."""

    def handle_one_request(self):
        self.server.attempts += 1
        return super().handle_one_request()

    def do_POST(self):
        self.send_response(503)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_GET = do_POST

    def log_message(self, *args):
        return None


def references(value, run_id):
    if isinstance(value, dict):
        if value.get("run_id") == run_id and value.get("status") == "completed":
            return True
        return any(references(child, run_id) for child in value.values())
    if isinstance(value, list):
        return any(references(child, run_id) for child in value)
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--http-case-log", type=Path, required=True)
    args = parser.parse_args()
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    raw_log = args.http_case_log.read_bytes()
    log = raw_log.decode(
        "utf-16" if raw_log.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    )
    first = json.loads(log.splitlines()[0])
    original_id = urlsplit(first["url"]).path.rsplit("/", 1)[-1]
    base = metadata["base"]
    session = requests.Session()
    response = session.get(base + "/api/v1/auto_login", timeout=20)
    response.raise_for_status()
    session.headers["Authorization"] = "Bearer " + response.json()["access_token"]
    response = session.get(base + "/api/v1/flows/" + original_id, timeout=20)
    response.raise_for_status()
    original = response.json()
    native = next(
        node for node in original["data"]["nodes"] if node["data"]["type"] == "MCPTools"
    )
    name = native["data"]["node"]["template"]["mcp_server"]["value"]["name"]
    response = session.get(base + "/api/v2/mcp/servers/" + name, timeout=20)
    response.raise_for_status()
    address = urlsplit(response.json()["url"])
    if address.hostname != "127.0.0.1":
        raise RuntimeError("owned_loopback_endpoint_required")
    runs = Path(metadata["state"]) / "runner/runs"
    candidates = []
    for path in runs.glob("*/record.json"):
        record = json.loads(path.read_text())
        if record.get("status") == "completed" and record.get("mcp_manifest"):
            candidates.append((path.stat().st_mtime, record))
    record = max(candidates, key=lambda item: item[0])[1]
    before = {path.parent.name for path in runs.glob("*/record.json")}
    server = ThreadingHTTPServer(("127.0.0.1", address.port), UnavailableServer)
    server.attempts = 0
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def submit(flow):
        flow.pop("id", None)
        response = session.post(base + "/api/v1/flows/", json=flow, timeout=20)
        response.raise_for_status()
        identifier = response.json()["id"]
        return session.post(
            base + "/api/v1/run/session/" + identifier,
            json={
                "input_value": "",
                "input_type": "chat",
                "output_type": "any",
                "output_component": flow["data"]["nodes"][-1]["id"],
            },
            timeout=60,
        )

    try:
        for operation in ("status", "cancel"):
            flow = deepcopy(original)
            flow["name"] = "MCP unavailable upstream " + operation
            agent = next(
                node
                for node in flow["data"]["nodes"]
                if "operation" in node["data"]["node"]["template"]
            )
            fields = agent["data"]["node"]["template"]
            fields["operation"]["value"] = operation
            fields["run_reference_json"]["value"] = json.dumps(
                {"provider": metadata["provider"], "run_id": record["run_id"]}
            )
            response = submit(flow)
            matched = response.ok and references(response.json(), record["run_id"])
            print(
                json.dumps(
                    {
                        "stage": "control_result",
                        "provider": metadata["provider"],
                        "operation": operation,
                        "http_status": response.status_code,
                        "completed_reference_returned": matched,
                        "upstream_attempts": server.attempts,
                    }
                ),
                flush=True,
            )
            if not matched or server.attempts:

                def shape(value, depth=0):
                    if depth > 5:
                        return type(value).__name__
                    if isinstance(value, dict):
                        return {
                            key: shape(child, depth + 1) for key, child in value.items()
                        }
                    if isinstance(value, list):
                        return [shape(child, depth + 1) for child in value[:1]]
                    return type(value).__name__

                print(
                    json.dumps(
                        {
                            "stage": "control_response_shape",
                            "shape": shape(response.json()),
                        }
                    ),
                    flush=True,
                )
                return 1
        # Falsifier: actually building this same native Toolset contacts the
        # unavailable server. No provider or model is dispatched in this graph.
        flow = deepcopy(original)
        flow["name"] = "MCP unavailable upstream falsifier"
        flow["data"]["nodes"] = [deepcopy(native)]
        flow["data"]["edges"] = []
        import langflow
        from lfx.components.models_and_agents.mcp_component import MCPToolsComponent
        from lfx.services.manager import get_service_manager
        from lfx.services.schema import ServiceType
        from lfx.services.settings.service import SettingsService
        from lfx.services.settings.base import Settings
        from lfx.services.settings.auth import AuthSettings

        with tempfile.TemporaryDirectory() as directory:
            get_service_manager().services[ServiceType.SETTINGS_SERVICE] = (
                SettingsService(
                    Settings(config_dir=directory), AuthSettings(CONFIG_DIR=directory)
                )
            )
            default = MCPToolsComponent().to_frontend_node()["data"]["node"]
        leaf = flow["data"]["nodes"][0]["data"]["node"]
        leaf["tool_mode"] = False
        leaf["outputs"] = default["outputs"]
        leaf["base_classes"] = default["base_classes"]
        leaf["template"]["tool"]["value"] = "read_marker"
        leaf["template"]["tools_metadata"]["show"] = False
        response = submit(flow)
        no_new_runs = before == {
            path.parent.name for path in runs.glob("*/record.json")
        }
        print(
            json.dumps(
                {
                    "stage": "control_falsifier",
                    "provider": metadata["provider"],
                    "http_status": response.status_code,
                    "upstream_attempts": server.attempts,
                    "no_new_agent_runs": no_new_runs,
                }
            ),
            flush=True,
        )
        return 0 if server.attempts > 0 and not response.ok and no_new_runs else 1
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
