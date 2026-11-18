"""Execute our saved graph through native Codex and retain normal scoped activity."""
import asyncio
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import threading
import time
import requests

ROOT = Path("C:/CodeWorkspace/laomedo")
APP = ROOT / ".tools/worktrees/assistant-291"
META = json.loads((ROOT / ".tools/assistant-291-live.json").read_text())
CHECK = json.loads((ROOT / ".tools/activity-295-own-graph.json").read_text())
STATE = Path(META["state"]) / "activity-295-native"
os.environ.update(PYTHONPATH=str(APP / "src"), LAOMEDO_AGENT_ACTIVITY_DB=str(Path(META["state"]) / "activity.db"))
sys.path.insert(0, str(APP / "src"))

def main():
    import langflow
    from lfx.services.manager import get_service_manager
    from lfx.services.schema import ServiceType
    from lfx.services.settings.service import SettingsService
    from lfx.services.settings.base import Settings
    from lfx.services.settings.auth import AuthSettings
    from laomedo.agents.agents.codex.agent import CodexAgent
    from laomedo.host.runner.http.server import RunnerServer
    from lfx.graph.graph.base import Graph
    STATE.mkdir(parents=True, exist_ok=True)
    config = str(STATE / "config")
    Path(config).mkdir(exist_ok=True)
    get_service_manager().services[ServiceType.SETTINGS_SERVICE] = SettingsService(Settings(config_dir=config), AuthSettings(CONFIG_DIR=config))
    session = requests.Session()
    base = META["base"]
    session.headers["Authorization"] = "Bearer " + session.get(base + "/api/v1/auto_login").json()["access_token"]
    response = session.get(base + "/api/v1/flows/" + CHECK["flow"], timeout=30)
    response.raise_for_status()
    flow = response.json()
    native = runpy.run_path(str(ROOT / ".tools/worktrees/docker-acceptance-exp/experiments/docker-boundary-277/acceptance.py"))
    source = STATE / "repository/source"
    source.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--quiet", str(source.parent)], check=True)
    agent = CodexAgent(STATE / "runner", Path(META["state"]) / "registry", source,
                       lease_service=Path(META["state"]) / "lease", **native["session_login"]())
    server = RunnerServer(agent, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    token = STATE / "runner-token"
    token.write_text(agent.api_token)
    os.environ["LAOMEDO_RUNNER_TOKEN_FILE"] = str(token)
    try:
        flow["data"]["nodes"][0]["data"]["node"]["template"]["runner_url"]["value"] = "http://127.0.0.1:" + str(server.server_port)
        graph = Graph.from_payload(flow, flow_id=flow["id"], user_id=flow["user_id"])
        print(json.dumps({"stage": "native_graph_started", "flow": flow["id"]}), flush=True)
        asyncio.run(graph.arun(inputs=[{}], outputs=["agent"]))
        time.sleep(3)
        print(json.dumps({"stage": "native_graph_completed"}), flush=True)
    finally:
        server.shutdown()
        server.server_close()

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        import traceback
        print(json.dumps({"stage": "incomplete", "error_type": type(error).__name__, "frames": [{"file": Path(f.filename).name, "function": f.name, "line": f.lineno} for f in traceback.extract_tb(error.__traceback__)]}), flush=True)
        raise SystemExit(1)
