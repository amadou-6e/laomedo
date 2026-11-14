"""Execute one real native graph/provider/transport case; no credential output."""

import argparse
import json
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
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--cancel", action="store_true")
    args = parser.parse_args()
    if args.resume and args.cancel:
        parser.error("Use one lifecycle check at a time.")
    root = args.implementation.resolve()
    sys.path.insert(0, str(root / "src"))
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    initial = json.loads(Path(metadata["graph_file"]).read_text(encoding="utf-8"))
    effort = initial["data"]["nodes"][0]["data"]["node"]["template"]["effort"]["value"]
    private = Path(metadata["state"])
    case = uuid4().hex[:12]
    state = private / ("mcp-case-" + case + ".json")
    marker = "mcp-280-" + uuid4().hex
    state.write_text(
        json.dumps(
            {"marker": marker, "calls": 0, "unselected_calls": 0, "hold": args.cancel}
        )
    )
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
                workflow="resume" if args.resume else "fresh",
                follow_up="Call the connected external MCP marker tool exactly once again. Reply only with its returned marker. Do not use commands, files or delegation.",
            )
            agent = flow["data"]["nodes"][0]
            agents = list(flow["data"]["nodes"])
            if not args.resume:
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
            for target in agents:
                flow["data"]["edges"].append(
                    edge(mcp, native["outputs"][0]["name"], target, "mcp_tools")
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
        cancel_sent = False
        while time.monotonic() < deadline:
            records = [json.loads(p.read_text()) for p in runs.glob("*/record.json")]
            matching = [
                r
                for r in records
                if r.get("mcp_manifest") and r.get("run_id") not in prior
            ]
            if matching:
                record = max(matching, key=lambda r: r.get("created_at", ""))
                observed = json.loads(state.read_text())
                if args.cancel and not cancel_sent and observed.get("entered"):
                    token = (private / "runner/api-token").read_text().strip()
                    cancelled = requests.post(
                        metadata["runner_url"]
                        + "/v1/runs/"
                        + record["run_id"]
                        + "/cancel",
                        headers={"Authorization": "Bearer " + token},
                        json={},
                        timeout=20,
                    )
                    cancelled.raise_for_status()
                    cancel_sent = True
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
            "resume": args.resume,
            "cancel_requested": cancel_sent,
            "tool_entered": observed.get("entered", 0),
            "native_session_present": bool(record.get("thread_id")),
            "attempt_count": len(
                list((runs / record["run_id"] / "activity-attempts").glob("*.json"))
            ),
        }
        print(json.dumps(result), flush=True)
        if args.cancel:
            return (
                0
                if cancel_sent
                and result["status"] == "cancelled"
                and result["tool_entered"] == 1
                and result["unselected_calls"] == 0
                else 1
            )
        return (
            0
            if result["status"] == "completed"
            and result["selected_calls"] == (2 if args.resume else 1)
            and result["unselected_calls"] == 0
            and result["marker_matches"]
            and result["manifest_tools"] == 1
            and (
                not args.resume
                or (result["native_session_present"] and result["attempt_count"] == 2)
            )
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
