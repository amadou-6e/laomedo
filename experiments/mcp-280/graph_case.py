"""Execute one real native graph/provider/transport case; no credential output."""

import argparse
import copy
import json
from pathlib import Path
import runpy
import socket
import subprocess
import sys
import tempfile
import time
import threading
from uuid import uuid4

import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--transport", choices=("http", "stdio"), required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--cancel", action="store_true")
    parser.add_argument("--with-skill", action="store_true")
    parser.add_argument("--two-servers", action="store_true")
    parser.add_argument("--audit-cleanup", action="store_true")
    parser.add_argument("--shutdown", action="store_true")
    parser.add_argument("--upstream-auth", action="store_true")
    args = parser.parse_args()
    if args.resume and args.cancel:
        parser.error("Use one lifecycle check at a time.")
    if args.shutdown and (args.resume or args.cancel or not args.audit_cleanup):
        parser.error("Shutdown requires a separate preview with cleanup audit enabled.")
    if args.upstream_auth and (
        args.transport != "http"
        or not args.audit_cleanup
        or args.shutdown
        or args.cancel
        or args.resume
    ):
        parser.error(
            "Upstream credential acceptance uses fresh HTTP with cleanup audit."
        )
    if args.two_servers and (args.transport != "stdio" or args.cancel or args.resume):
        parser.error("Combined-server acceptance uses fresh STDIO execution.")
    root = args.implementation.resolve()
    sys.path.insert(0, str(root / "src"))
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    initial = json.loads(Path(metadata["graph_file"]).read_text(encoding="utf-8"))
    effort = initial["data"]["nodes"][0]["data"]["node"]["template"]["effort"]["value"]
    private = Path(metadata["state"])
    case = uuid4().hex[:12]
    state = private / ("mcp-case-" + case + ".json")
    marker = "mcp-280-" + uuid4().hex
    upstream_canary = "mcp-280-private-" + uuid4().hex if args.upstream_auth else None
    state.write_text(
        json.dumps(
            {
                "marker": marker,
                "calls": 0,
                "unselected_calls": 0,
                "hold": args.cancel or args.shutdown,
                "upstream_canary": upstream_canary,
            }
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
        if upstream_canary:
            config["headers"] = {"X-MCP-Validation-Key": upstream_canary}
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
    proxy = None
    runner_url = metadata["runner_url"]
    if upstream_canary:
        from proxy import TaskPayloadProxy

        proxy = TaskPayloadProxy(runner_url, upstream_canary)
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        runner_url = "http://127.0.0.1:" + str(proxy.server_port)
    try:
        login = session.get(base + "/api/v1/auto_login", timeout=20)
        login.raise_for_status()
        session.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        name = "mcp-280-" + case
        response = session.post(
            base + "/api/v2/mcp/servers/" + name, json=config, timeout=30
        )
        response.raise_for_status()
        states = [state]
        second_name = None
        if args.two_servers:
            second_name = name + "-second"
            second_state = private / ("mcp-case-" + case + "-second.json")
            second_state.write_text(state.read_text(encoding="utf-8"), encoding="utf-8")
            states.append(second_state)
            second_config = {
                "command": sys.executable,
                "args": [str(server_file), "--state", str(second_state)],
            }
            response = session.post(
                base + "/api/v2/mcp/servers/" + second_name,
                json=second_config,
                timeout=30,
            )
            response.raise_for_status()
        reference = None
        if args.with_skill:
            from laomedo.skills.registry.store import SkillStore

            skill_source = private / ("mcp-skill-" + case)
            skill_source.mkdir()
            skill_id = "mcp-validation-" + case
            (skill_source / "SKILL.md").write_text(
                f"---\nname: {skill_id}\ndescription: Harmless acceptance guidance.\n---\n"
                "Use only the selected external marker readers requested by the user. "
                "Do not edit files or delegate. Reply only with the marker.\n",
                encoding="utf-8",
            )
            reference = SkillStore(private / "registry").import_skill(
                skill_id, skill_source
            )

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
                runner_url=runner_url,
                task=(
                    "Use both connected external MCP marker reader tools, one from each server. "
                    "Call each exactly once, with no arguments. Both return the same marker. "
                    "Reply only with that marker. Follow the connected Skill. "
                    "Do not run commands, edit files, delegate or call any other tool."
                    if args.two_servers
                    else "Use the connected external MCP tool whose description reads the validation marker. Call it exactly once, with no arguments. Reply only with the returned marker. Do not run commands, edit files, delegate or call any other tool."
                ),
                reference=reference,
                workflow="resume" if args.resume else "fresh",
                follow_up="Call the connected external MCP marker tool exactly once again. Reply only with its returned marker. Do not use commands, files or delegation.",
            )
            agent = flow["data"]["nodes"][0]
            agents = [
                node
                for node in flow["data"]["nodes"]
                if "mcp_tools" in node["data"]["node"]["template"]
            ]
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
            if second_name:
                second = copy.deepcopy(mcp)
                second["id"] = second["data"]["id"] = "mcp-server-second"
                second["position"] = {"x": -400, "y": 500}
                second["data"]["node"]["template"]["mcp_server"]["value"] = {
                    "name": second_name
                }
                flow["data"]["nodes"].insert(1, second)
                for target in agents:
                    flow["data"]["edges"].append(
                        edge(second, native["outputs"][0]["name"], target, "mcp_tools")
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
        shutdown_sent = False
        shutdown_observed = False
        capabilities = {}
        while time.monotonic() < deadline:
            if args.audit_cleanup:
                for connection_file in (private / "mcp").glob("*.json"):
                    try:
                        connection = json.loads(
                            connection_file.read_text(encoding="utf-8")
                        )
                    except FileNotFoundError:
                        continue
                    capabilities[connection_file] = connection
            records = [json.loads(p.read_text()) for p in runs.glob("*/record.json")]
            matching = [
                r
                for r in records
                if r.get("mcp_manifest") and r.get("run_id") not in prior
            ]
            if matching:
                record = max(matching, key=lambda r: r.get("created_at", ""))
                observed = json.loads(state.read_text())
                if args.shutdown and not shutdown_sent and observed.get("entered"):
                    (private / "stop-preview").write_text(
                        "graceful shutdown acceptance\n"
                    )
                    shutdown_sent = True
                if (
                    args.shutdown
                    and shutdown_sent
                    and capabilities
                    and all(not path.exists() for path in capabilities)
                ):
                    try:
                        requests.get(base + "/health", timeout=1)
                    except requests.ConnectionError:
                        shutdown_observed = True
                        break
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
        observations = [json.loads(path.read_text()) for path in states]
        observed = observations[0]
        result = {
            "stage": "case_result",
            "provider": metadata["provider"],
            "transport": args.transport,
            "status": record["status"],
            "error_category": record.get("error_category"),
            "selected_calls": sum(item["calls"] for item in observations),
            "selected_calls_per_server": [item["calls"] for item in observations],
            "unselected_calls": sum(item["unselected_calls"] for item in observations),
            "marker_matches": (record.get("answer") or "").strip() == marker,
            "manifest_tools": len(record["mcp_manifest"]["tools"]),
            "resume": args.resume,
            "with_skill": args.with_skill,
            "server_count": len(states),
            "cancel_requested": cancel_sent,
            "shutdown_requested": shutdown_sent,
            "shutdown_observed": shutdown_observed,
            "upstream_auth_observed": observed.get("upstream_auth_observed", False),
            "tool_entered": observed.get("entered", 0),
            "native_session_present": bool(record.get("thread_id")),
            "attempt_count": len(
                list((runs / record["run_id"] / "activity-attempts").glob("*.json"))
            ),
        }
        print(json.dumps(result), flush=True)
        if args.audit_cleanup:
            deadline = time.monotonic() + 15
            while (
                any(path.exists() for path in capabilities)
                and time.monotonic() < deadline
            ):
                time.sleep(0.1)
            refused = []
            for path, connection in capabilities.items():
                endpoint = (
                    f"http://{connection['bind']}:{connection['port']}/"
                    + connection["registration"]["registration_id"]
                    + "/mcp"
                )
                try:
                    response = requests.get(
                        endpoint,
                        headers={"Authorization": "Bearer " + connection["token"]},
                        timeout=10,
                    )
                    refused.append(
                        response.status_code == 403
                        and response.json().get("code")
                        == "mcp_registration_unavailable"
                        and not path.exists()
                    )
                except requests.ConnectionError:
                    refused.append(args.shutdown and not path.exists())
            audit = {
                "stage": "cleanup_audit",
                "provider": metadata["provider"],
                "captured_capabilities": len(capabilities),
                "all_files_removed_and_capabilities_refused": bool(refused)
                and all(refused),
            }
            print(json.dumps(audit), flush=True)
            if not audit["all_files_removed_and_capabilities_refused"]:
                return 1
            if args.shutdown:
                return 0 if shutdown_observed and result["tool_entered"] == 1 else 1
            exported = session.get(base + "/api/v1/flows/" + flow_id, timeout=20)
            exported.raise_for_status()
            run_directory = runs / record["run_id"]
            public_files = [
                run_directory / name
                for name in ("record.json", "raw-events.jsonl", "activity-events.jsonl")
            ]
            for concern in ("activity-attempts", "diagnostics"):
                public_files.extend((run_directory / concern).glob("*.json"))
            blobs = [exported.content] + [
                path.read_bytes() for path in public_files if path.is_file()
            ]
            secrets = [value["token"].encode() for value in capabilities.values()]
            secrets.append((private / "runner/api-token").read_bytes().strip())
            if upstream_canary:
                secrets.append(upstream_canary.encode())
            clean = all(secret not in blob for secret in secrets for blob in blobs)
            print(
                json.dumps(
                    {
                        "stage": "privacy_audit",
                        "provider": metadata["provider"],
                        "export_and_record_blobs": len(blobs),
                        "scoped_capabilities_and_runner_token_absent": clean,
                        "upstream_canary_absent": clean if upstream_canary else None,
                        "task_payload_requests": proxy.task_requests if proxy else 0,
                        "task_payload_canary_absent": (
                            not proxy.canary_leaked if proxy else None
                        ),
                    }
                ),
                flush=True,
            )
            if not clean:
                return 1
            if upstream_canary and (
                not observed.get("upstream_auth_observed")
                or not proxy.task_requests
                or proxy.canary_leaked
            ):
                return 1
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
            and result["selected_calls_per_server"]
            == [2 if args.resume else 1] * len(states)
            and result["unselected_calls"] == 0
            and result["marker_matches"]
            and result["manifest_tools"] == len(states)
            and (
                not args.resume
                or (result["native_session_present"] and result["attempt_count"] == 2)
            )
            else 1
        )
    finally:
        if proxy is not None:
            proxy.shutdown()
            proxy.server_close()
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
