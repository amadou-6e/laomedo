"""Real official Playwright MCP through the maintained Codex graph."""

import copy
import json
from pathlib import Path
import runpy
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import requests


def main():
    root = Path(sys.argv[1]).resolve()
    metadata = json.loads(Path(sys.argv[2]).read_text())
    sys.path.insert(0, str(root / "src"))
    import tempfile
    import langflow
    from lfx.services.manager import get_service_manager
    from lfx.services.schema import ServiceType
    from lfx.services.settings.service import SettingsService
    from lfx.services.settings.base import Settings
    from lfx.services.settings.auth import AuthSettings
    from lfx.components.models_and_agents.mcp_component import MCPToolsComponent
    from lfx.io import ToolsInput

    private = Path(metadata["state"])
    marker = "browser-" + uuid4().hex
    page = private / ("playwright-" + uuid4().hex)
    page.mkdir()
    (page / "index.html").write_text(
        "<!doctype html><title>MCP browser acceptance</title><h1>Browser acceptance</h1>"
        "<button onclick=\"document.getElementById('result').textContent='"
        + marker
        + '\'">Reveal result</button><p id="result">Not revealed</p>'
    )
    from functools import partial

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(page))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/index.html"
    session = requests.Session()
    base = metadata["base"]
    login = session.get(base + "/api/v1/auto_login", timeout=20)
    login.raise_for_status()
    session.headers["Authorization"] = "Bearer " + login.json()["access_token"]
    name = "playwright-chrome-280-" + uuid4().hex[:8]
    config = {
        "command": "npx",
        "args": [
            "-y",
            "@playwright/mcp@0.0.85",
            "--browser",
            "chrome",
            "--isolated",
            "--headless",
            "--output-dir",
            str(page / "output"),
        ],
    }
    registered = session.post(
        base + "/api/v2/mcp/servers/" + name, json=config, timeout=90
    )
    registered.raise_for_status()
    with tempfile.TemporaryDirectory() as directory:
        get_service_manager().services[ServiceType.SETTINGS_SERVICE] = SettingsService(
            Settings(config_dir=directory), AuthSettings(CONFIG_DIR=directory)
        )
        build = runpy.run_path(str(root / "examples/agents/build_flow.py"))["build"]
        flow = build(
            provider=metadata["provider"],
            model=metadata["model"],
            effort="low",
            runner_url=metadata["runner_url"],
            task=f"Use only the connected external Playwright MCP tools. Navigate to {url}, click the Reveal result button using its snapshot reference, and reply only with the revealed result. Do not use commands, files, code evaluation, delegation or other tools.",
        )
        agent = flow["data"]["nodes"][0]
        agent["data"]["node"]["template"]["operation"]["value"] = "start"
        component = MCPToolsComponent()
        native = component.to_frontend_node()["data"]["node"]
        native["tool_mode"] = True
        native["template"]["mcp_server"]["value"] = {"name": name}
        native["template"]["use_cache"]["value"] = False
        selected = ["browser_navigate", "browser_click", "browser_snapshot"]
        native["template"]["tools_metadata"] = ToolsInput(
            name="tools_metadata",
            display_name="Actions",
            value=[
                {"name": tool, "description": tool, "tags": [tool], "status": True}
                for tool in selected
            ],
        ).to_dict()
        native["outputs"] = [component._build_tool_output().model_dump(mode="json")]
        native["outputs"][0]["types"] = ["Tool"]
        mcp = {
            "id": "playwright",
            "type": "genericNode",
            "position": {"x": -400, "y": 0},
            "data": {"id": "playwright", "type": "MCPTools", "node": native},
        }
        flow["data"]["nodes"].insert(0, mcp)
        edge = runpy.run_path(str(root / "examples/graph.py"))["edge"]
        flow["data"]["edges"].append(
            edge(mcp, native["outputs"][0]["name"], agent, "mcp_tools")
        )
    flow["name"] = "Real Playwright MCP — isolated Chrome"
    flow.pop("id", None)
    created = session.post(base + "/api/v1/flows/", json=flow, timeout=30)
    created.raise_for_status()
    flow_id = created.json()["id"]
    print(
        json.dumps(
            {
                "graph": base + "/flow/" + flow_id,
                "package": "@playwright/mcp@0.0.85",
                "browser": "chrome",
                "selected_tools": selected,
            }
        ),
        flush=True,
    )
    runs = private / "runner/runs"
    prior = {p.parent.name for p in runs.glob("*/record.json")}
    try:
        started = session.post(
            base + "/api/v1/run/session/" + flow_id,
            json={"input_value": "", "input_type": "chat", "output_type": "any"},
            timeout=120,
        )
        started.raise_for_status()
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            records = [
                json.loads(p.read_text())
                for p in runs.glob("*/record.json")
                if p.parent.name not in prior
            ]
            if records:
                record = max(records, key=lambda r: r.get("created_at", ""))
                if record.get("status") not in ("running", "queued", "starting"):
                    result = {
                        "status": record.get("status"),
                        "marker_matches": (record.get("answer") or "").strip()
                        == marker,
                        "manifest_tools": len(
                            record.get("mcp_manifest", {}).get("tools", [])
                        ),
                        "run_id": record.get("run_id"),
                        "category": record.get("category"),
                    }
                    print(json.dumps(result), flush=True)
                    return (
                        0
                        if result["status"] == "completed" and result["marker_matches"]
                        else 1
                    )
            time.sleep(1)
        raise TimeoutError("playwright_graph_acceptance_timeout")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
