"""Isolated assistant acceptance app. Opening never submits inference."""

import json
import os
from pathlib import Path
import subprocess
import sys
import socket
import tempfile
import time
import threading
from urllib.parse import urlsplit

WORKSPACE = Path("C:/CodeWorkspace/laomedo")
IMPLEMENTATION = WORKSPACE / ".tools/worktrees/assistant-282"
metadata_path = WORKSPACE / ".tools/assistant-282-live.json"
previous = json.loads(metadata_path.read_text()) if "--resume" in sys.argv else None
STATE = Path(previous["state"]) if previous else Path(tempfile.mkdtemp(prefix="laomedo-assistant-282-"))
if previous:
    PORT = urlsplit(previous["base"]).port
else:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        PORT = listener.getsockname()[1]
os.environ.update({
    "PYTHONPATH": str(IMPLEMENTATION / "src"),
    "LANGFLOW_CONFIG_DIR": str(STATE / "app"),
    "LFX_CONFIG_DIR": str(STATE / "app"),
    "LANGFLOW_DATABASE_URL": "sqlite:///" + (STATE / "app/flow.db").as_posix(),
    "LANGFLOW_FRONTEND_PATH": str(WORKSPACE / ".tools/assistant-282-upstream/src/frontend/build"),
    "LANGFLOW_COMPONENTS_PATH": str(IMPLEMENTATION / "components"),
    "LAOMEDO_COMPONENT_DIR": str(IMPLEMENTATION / "components/laomedo"),
    "LANGFLOW_AUTO_LOGIN": "true",
    "LANGFLOW_DO_NOT_TRACK": "true",
    "LAOMEDO_SKILL_STORE": str(STATE / "registry"),
    "LAOMEDO_AGENT_ACTIVITY_DB": str(STATE / "activity.db"),
    "LAOMEDO_MCP_DIRECTORY": str(STATE / "mcp"),
    "LAOMEDO_ASSISTANT_APP_URL": f"http://127.0.0.1:{PORT}",
    "LAOMEDO_ASSISTANT_STATE_ROOT": str(STATE / "assistant"),
    "LAOMEDO_RUNNER_SERVICE_FILE": str(STATE / "runner-service.json"),
})
sys.path.insert(0, str(IMPLEMENTATION / "src"))
for name in ("app", "registry", "source"):
    (STATE / name).mkdir(exist_ok=True)
(STATE / "runner-service.json").write_text(json.dumps({"provider": "codex", "state": str(STATE / "configured-runner"), "skill_store": str(STATE / "registry"), "source": str(STATE / "source"), "port": 17882, "lease_service": str(STATE / "lease")}), encoding="utf-8")
metadata_path.write_text(json.dumps(previous or {"state": str(STATE), "base": f"http://127.0.0.1:{PORT}"}), encoding="utf-8")
(STATE / "stop-acceptance").unlink(missing_ok=True)
lease_log = (STATE / "lease.log").open("wb")
lease = subprocess.Popen([sys.executable, "-m", "laomedo.host.leases.service_cli", "serve", "--state", str(STATE / "lease")], stdout=lease_log, stderr=lease_log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
try:
    deadline = time.monotonic() + 30
    while not (STATE / "lease/service.json").is_file():
        if lease.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("acceptance_lease_unavailable")
        time.sleep(.2)
    import laomedo
    import uvicorn
    laomedo.__path__.append(str(IMPLEMENTATION / "components/laomedo"))
    os.chdir(STATE)
    server = uvicorn.Server(uvicorn.Config("laomedo.integrations.langflow.viewer:create_app", factory=True, host="127.0.0.1", port=PORT))
    def watch_stop():
        while not server.should_exit:
            if (STATE / "stop-acceptance").exists():
                server.should_exit = True
                return
            time.sleep(.2)
    threading.Thread(target=watch_stop, daemon=True).start()
    server.run()
finally:
    lease.terminate()
    lease.wait(timeout=20)
    lease_log.close()
