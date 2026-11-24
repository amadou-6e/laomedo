"""Start the stopped pilot preview with its existing normal profile and files."""

import json
import os
from pathlib import Path
import socket
import subprocess


def main():
    root = Path("C:/CodeWorkspace/laomedo")
    source = root / ".tools/worktrees/repository-storage-309"
    upstream = root / ".tools/assistant-282-upstream"
    private = (
        Path(os.environ["LOCALAPPDATA"])
        / "Laomedo/acceptance/assistant-saved-293-01a1ba85"
    )
    marker = json.loads(
        (private / "local-profiles.json").read_text(encoding="utf-8-sig")
    )
    if marker.get("purpose") != "laomedo-local-profiles" or marker.get("port") != 55753:
        raise SystemExit("wrong_preview_marker")
    if (
        not (private / "langflow/flow.db").is_file()
        or not (upstream / "src/frontend/build/index.html").is_file()
    ):
        raise SystemExit("preview_state_or_build_missing")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 55753))
    allowed = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "LOCALAPPDATA",
        "APPDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PROGRAMDATA",
        "COMSPEC",
        "HOMEDRIVE",
        "HOMEPATH",
        "PATHEXT",
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_CONFIG",
    }
    environment = {
        key: value for key, value in os.environ.items() if key.upper() in allowed
    }
    environment.update(
        {
            "PYTHONPATH": os.pathsep.join(
                str(path)
                for path in (
                    source / "src",
                    upstream / "src/backend/base",
                    upstream / "src/lfx/src",
                )
            ),
            "LANGFLOW_CONFIG_DIR": str(private / "langflow"),
            "LFX_CONFIG_DIR": str(private / "langflow"),
            "LANGFLOW_DATABASE_URL": "sqlite:///"
            + (private / "langflow/flow.db").as_posix(),
            "LANGFLOW_AUTO_LOGIN": "false",
            "LANGFLOW_SKIP_AUTH_AUTO_LOGIN": "false",
            "LANGFLOW_ENABLE_SIGNUP": "false",
            "LANGFLOW_NEW_USER_IS_ACTIVE": "true",
            "LANGFLOW_ENABLE_SUPERUSER_CLI": "false",
            "LANGFLOW_API_KEY_SOURCE": "db",
            "LANGFLOW_EXTERNAL_AUTH_ENABLED": "false",
            "LANGFLOW_FRONTEND_PATH": str(upstream / "src/frontend/build"),
            "LANGFLOW_COMPONENTS_PATH": str(source / "components"),
            "LAOMEDO_COMPONENT_DIR": str(source / "components/laomedo"),
            "LAOMEDO_SKILL_STORE": str(private / "registry"),
            "LAOMEDO_AGENT_ACTIVITY_DB": str(private / "activity.db"),
            "LANGFLOW_DO_NOT_TRACK": "true",
            "LANGFLOW_CORS_ORIGINS": '["http://127.0.0.1:55753"]',
            "LANGFLOW_CORS_ALLOW_CREDENTIALS": "true",
            "LAOMEDO_LOCAL_PROFILE_PORT": "55753",
            "LAOMEDO_LOCAL_PROFILE_RUNTIME": str(private),
            "LAOMEDO_ASSISTANT_APP_URL": "http://127.0.0.1:55753",
            "LAOMEDO_ASSISTANT_STATE_ROOT": str(private / "assistant"),
            "LAOMEDO_ASSISTANT_STORAGE_ROOT": str(private / "project-storage"),
            "LAOMEDO_PROVIDER_SOURCE_WORKSPACE": str(source),
        }
    )
    entry = """from pathlib import Path
import os
import laomedo
import uvicorn
from laomedo.integrations.langflow.local_profiles.runtime import LocalProfileRuntime
from laomedo.integrations.langflow.viewer import create_app
laomedo.__path__.append(os.environ['LAOMEDO_COMPONENT_DIR'])
runtime=LocalProfileRuntime(Path(os.environ['LAOMEDO_LOCAL_PROFILE_RUNTIME']), provider_source=Path(os.environ['LAOMEDO_PROVIDER_SOURCE_WORKSPACE']))
app=create_app(profile_runtime=runtime)
uvicorn.run(app,host='127.0.0.1',port=55753,access_log=False)
"""
    with (private / "repository-storage-preview.log").open("ab") as output:
        child = subprocess.Popen(
            [str(root / ".venv/Scripts/python.exe"), "-u", "-c", entry],
            cwd=private,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=output,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    (private / "repository-storage-preview-pid").write_text(
        str(child.pid), encoding="utf-8"
    )
    print(
        json.dumps(
            {"preview_pid": child.pid, "base": "http://127.0.0.1:55753", "ready": False}
        )
    )


if __name__ == "__main__":
    main()
