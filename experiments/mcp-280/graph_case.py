"""Execute one real native graph/provider/transport case; no credential output."""

import argparse
import json
import os
from pathlib import Path
import runpy
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--transport", choices=("http", "stdio"), required=True)
    args = parser.parse_args()
    root = args.implementation.resolve()
    sys.path.insert(0, str(root / "src"))
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    initial = json.loads(Path(metadata["graph_file"]).read_text(encoding="utf-8"))
    effort = initial["data"]["nodes"][0]["data"]["node"]["template"]["effort"]["value"]
    private = Path(metadata["state"])
    case = uuid4().hex[:12]
    state = private / ("mcp-case-" + case + ".json")
    marker = "mcp-280-" + uuid4().hex
    state.write_text(json.dumps({"marker": marker, "calls": 0, "unselected_calls": 0}))
    server_file = Path(__file__).with_name("server.py")
    config = {
        "command": sys.executable,
        "args": [str(server_file), "--state", str(state)],
    }
    process = None
    if args.transport == "http":
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen(
            [
                sys.executable,
                str(server_file),
                "--state",
                str(state),
                "--port",
                str(port),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        config = {"url": f"http://127.0.0.1:{port}/mcp"}
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("acceptance_server_unavailable")
    session = requests.Session()
    base = metadata["base"]
    try:
        login = session.get(base + "/api/v1/auto_login", timeout=20)
        login.raise_for_status()
        session.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        name = "mcp-280-" + case
        response = session.post(
            base + "/api/v2/mcp/servers/" + name, json=config, timeout=30
        )
        response.raise_for_status()

        import langflow
        from lfx.services.manager import get_service_manager
        from lfx.services.schema import ServiceType
        from lfx.services.settings.service import SettingsService
        from lfx.services.settings.base import Settings
        from lfx.services.settings.auth import AuthSettings
        from lfx.components.models_and_agents.mcp_component import MCPToolsComponent
        from lfx.io import ToolsInput

        with tempfile.TemporaryDirectory() as directory:
            get_service_manager().services[ServiceType.SETTINGS_SERVICE] = (
                SettingsService(
                    Settings(config_dir=directory), AuthSettings(CONFIG_DIR=directory)
                )
            )
            build = runpy.run_path(str(root / "examples/agents/build_flow.py"))["build"]
            flow = build(
                provider=metadata["provider"],
                model=metadata["model"],
                effort=effort,
                runner_url=metadata["runner_url"],
                task="Use the connected external MCP tool whose description reads the validation marker. Call it exactly once, with no arguments. Reply only with the returned marker. Do not run commands, edit files, delegate or call any other tool.",
            )
            agent = flow["data"]["nodes"][0]
            agent["data"]["node"]["template"]["operation"]["value"] = "start"
            component = MCPToolsComponent()
            native = component.to_frontend_node()["data"]["node"]
            native["tool_mode"] = True
            native["template"]["mcp_server"]["value"] = {"name": name}
            native["template"]["use_cache"]["value"] = False
            native["template"]["tools_metadata"] = ToolsInput(
                name="tools_metadata",
                display_name="Actions",
                value=[
                    {
                        "name": "read_marker",
                        "description": "Read the validation marker.",
                        "tags": ["read_marker"],
                        "status": True,
                    },
                    {
                        "name": "unselected_probe",
                        "description": "Unselected test tool.",
                        "tags": ["unselected_probe"],
                        "status": False,
                    },
                ],
            ).to_dict()
            native["outputs"] = [component._build_tool_output().model_dump(mode="json")]
            mcp = {
                "id": "mcp-server",
                "type": "genericNode",
                "position": {"x": -400, "y": 0},
                "data": {"id": "mcp-server", "type": "MCPTools", "node": native},
            }
            edge = runpy.run_path(str(root / "examples/graph.py"))["edge"]
            # Native Toolset output uses output_types in its serialized definition.
            native["outputs"][0]["types"] = ["Tool"]
            flow["data"]["nodes"].insert(0, mcp)
            flow["data"]["edges"].append(
                edge(mcp, native["outputs"][0]["name"], agent, "mcp_tools")
            )
        flow["name"] = f"MCP {metadata['provider']} {args.transport} validation"
        flow.pop("id", None)
        created = session.post(base + "/api/v1/flows/", json=flow, timeout=30)
        created.raise_for_status()
        flow_id = created.json()["id"]
        print(
            json.dumps({"stage": "graph_created", "url": base + "/flow/" + flow_id}),
            flush=True,
        )
        runs = private / "runner/runs"
        prior = {p.parent.name for p in runs.glob("*/record.json")}
        started = session.post(
            base + "/api/v1/run/session/" + flow_id,
            json={"input_value": "", "input_type": "chat", "output_type": "any"},
            timeout=120,
        )
        if not started.ok:
            text = started.text
            print(
                json.dumps(
                    {
                        "stage": "graph_failed",
                        "http_status": started.status_code,
                        "known_codes": [
                            word
                            for word in (
                                "mcp_native_tool_unsupported",
                                "mcp_private_state_unverified",
                                "mcp_app_lifetime_required",
                                "mcp_registration_unavailable",
                                "ssrf",
                                "User ID",
                                "Settings service",
                            )
                            if word in text
                        ],
                    }
                ),
                flush=True,
            )
            return 1
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            records = [json.loads(p.read_text()) for p in runs.glob("*/record.json")]
            matching = [
                r
                for r in records
                if r.get("mcp_manifest") and r.get("run_id") not in prior
            ]
            if matching:
                record = max(matching, key=lambda r: r.get("created_at", ""))
                if record["status"] in {
                    "completed",
                    "failed",
                    "cancelled",
                    "timeout",
                    "unknown",
                }:
                    break
            time.sleep(0.5)
        else:
            print(json.dumps({"stage": "runner_wait_expired"}))
            return 1
        observed = json.loads(state.read_text())
        result = {
            "stage": "case_result",
            "provider": metadata["provider"],
            "transport": args.transport,
            "status": record["status"],
            "error_category": record.get("error_category"),
            "selected_calls": observed["calls"],
            "unselected_calls": observed["unselected_calls"],
            "marker_matches": (record.get("answer") or "").strip() == marker,
            "manifest_tools": len(record["mcp_manifest"]["tools"]),
        }
        print(json.dumps(result), flush=True)
        return (
            0
            if result["status"] == "completed"
            and result["selected_calls"] == 1
            and result["unselected_calls"] == 0
            and result["marker_matches"]
            and result["manifest_tools"] == 1
            else 1
        )
    finally:
        if process is not None:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(
            json.dumps(
                {
                    "stage": "case_exception",
                    "type": type(error).__name__,
                    "code": getattr(error, "code", None),
                }
            ),
            flush=True,
        )
        raise SystemExit(1)
