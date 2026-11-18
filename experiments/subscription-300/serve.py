"""Resume the existing provider preview on17884 with the selected quota implementation."""

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path("C:/CodeWorkspace/laomedo")
APP = ROOT / ".tools/worktrees/subscription-300"
STATE = Path.home() / "AppData/Local/Temp/laomedo-provider-284-runtime"
FRONTEND = ROOT / ".tools/pr-readiness/300/frontend-stage"
SOURCE = Path.home() / "AppData/Local/Temp/laomedo-subscription-300-repository/source"
SOURCE.mkdir(parents=True, exist_ok=True)
subprocess.run(["git", "init", "--quiet", str(SOURCE.parent)], check=True)
os.environ.update(
    {
        "PYTHONPATH": str(APP / "src"),
        "LANGFLOW_CONFIG_DIR": str(STATE / "langflow"),
        "LFX_CONFIG_DIR": str(STATE / "langflow"),
        "LANGFLOW_DATABASE_URL": "sqlite:///" + (STATE / "langflow/flow.db").as_posix(),
        "LANGFLOW_FRONTEND_PATH": str(FRONTEND),
        "LANGFLOW_COMPONENTS_PATH": str(APP / "components"),
        "LAOMEDO_COMPONENT_DIR": str(APP / "components/laomedo"),
        "LAOMEDO_SKILL_STORE": str(STATE / "registry"),
        "LAOMEDO_AGENT_ACTIVITY_DB": str(STATE / "activity.db"),
        "LANGFLOW_AUTO_LOGIN": "false",
        "LANGFLOW_SKIP_AUTH_AUTO_LOGIN": "false",
        "LANGFLOW_ENABLE_SIGNUP": "false",
        "LANGFLOW_NEW_USER_IS_ACTIVE": "true",
        "LANGFLOW_API_KEY_SOURCE": "db",
        "LANGFLOW_EXTERNAL_AUTH_ENABLED": "false",
        "LANGFLOW_DO_NOT_TRACK": "true",
    }
)
sys.path.insert(0, str(APP / "src"))
import langflow
import uvicorn
from laomedo.integrations.langflow.local_profiles.runtime import LocalProfileRuntime
from laomedo.integrations.langflow.viewer import create_app

if "--check-settings" in sys.argv:
    from laomedo.integrations.langflow.local_profiles.admission import (
        ProfileRuntimeAdmission,
    )
    from langflow.services.deps import get_settings_service

    admission = ProfileRuntimeAdmission(STATE)
    admission.verify_settings(get_settings_service())
    if admission.verify_database(get_settings_service().auth_settings):
        raise RuntimeError("existing_profile_database_missing")
    print("Existing profile runtime admission passed; port17884/state preserved.")
    raise SystemExit(0)
app = create_app(LocalProfileRuntime(STATE, provider_source=SOURCE))
uvicorn.run(app, host="127.0.0.1", port=17884)
