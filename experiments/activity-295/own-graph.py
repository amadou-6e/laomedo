"""Create one real activity check in our own preview, without touching other apps."""
import json
import os
from pathlib import Path
import runpy
import sys
import traceback
import requests

ROOT = Path("C:/CodeWorkspace/laomedo")
APP = ROOT / ".tools/worktrees/assistant-291"
META = json.loads((ROOT / ".tools/assistant-291-live.json").read_text())
os.environ["PYTHONPATH"] = str(APP / "src")
sys.path.insert(0, str(APP / "src"))

def main():
    session = requests.Session()
    base = META["base"]
    login = session.get(base + "/api/v1/auto_login", timeout=20)
    login.raise_for_status()
    session.headers.update({"Authorization": "Bearer " + login.json()["access_token"], "Origin": base})
    build = runpy.run_path(str(APP / "examples/agents/build_flow.py"))["build"]
    from lfx.services.manager import get_service_manager
    from lfx.services.schema import ServiceType
    from lfx.services.settings.service import SettingsService
    from lfx.services.settings.base import Settings
    from lfx.services.settings.auth import AuthSettings
    config = str(ROOT / ".tools/activity-295-builder")
    Path(config).mkdir(parents=True, exist_ok=True)
    get_service_manager().services[ServiceType.SETTINGS_SERVICE] = SettingsService(Settings(config_dir=config), AuthSettings(CONFIG_DIR=config))
    flow = build(provider="codex", model="gpt-6-luna", effort="low", runner_url="http://127.0.0.1:17882",
                 task="Run pwd once, then reply exactly: Activity preview verified. Do not edit files or delegate.")
    flow["name"] = "Activity review - isolated preview"
    created = session.post(base + "/api/v1/flows/", json=flow, timeout=30)
    created.raise_for_status()
    flow_id = created.json()["id"]
    (ROOT / ".tools/activity-295-own-graph.json").write_text(json.dumps({"flow": flow_id, "base": base}))
    print(json.dumps({"stage": "created", "url": base + "/flow/" + flow_id}), flush=True)
    run = session.post(base + "/api/v1/run/session/" + flow_id,
                       json={"input_value": "", "input_type": "chat", "output_type": "any"}, timeout=240)
    print(json.dumps({"stage": "run", "http_status": run.status_code}), flush=True)
    run.raise_for_status()

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"stage": "incomplete", "error_type": type(error).__name__, "frames": [{"file": Path(f.filename).name, "function": f.name, "line": f.lineno} for f in traceback.extract_tb(error.__traceback__)]}), flush=True)
        raise SystemExit(1)
