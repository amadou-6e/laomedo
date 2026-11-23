"""Restart only the idle, owned chat preview while preserving its normal login state."""

import argparse
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPCookieProcessor

import psutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    arguments = parser.parse_args()
    root = Path("C:/CodeWorkspace/laomedo")
    source = root / ".tools/worktrees/repository-storage-309"
    base = "http://127.0.0.1:55753"
    process = psutil.Process(arguments.pid)
    if "assistant-saved-293-01a1ba85" not in process.cwd():
        raise SystemExit("wrong_preview_process")
    environment = process.environ()
    private = Path(environment["LANGFLOW_CONFIG_DIR"]).parent
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    opener.addheaders = [("Origin", base)]
    profiles = json.load(opener.open(base + "/api/v1/laomedo/profiles"))["profiles"]
    profile = next(row for row in profiles if row["name"].lower() == "amadou")
    pin = next(
        line.split("=", 1)[1].strip().strip("\"'")
        for line in (root / ".env").read_text(encoding="utf-8").splitlines()
        if line.startswith("LAOMEDO_PIN=")
    )
    opener.open(
        base + "/api/v1/login",
        data=urlencode({"username": profile["name"], "password": pin}).encode(),
    ).close()
    cursor = 0
    while True:
        payload = json.load(
            opener.open(
                base + "/api/v1/laomedo/assistant/conversations?cursor=" + str(cursor)
            )
        )
        if any(
            row["state"] in {"starting", "running", "stopping"}
            for row in payload["conversations"]
        ):
            raise SystemExit("preview_has_active_work")
        cursor = payload.get("next_cursor")
        if cursor is None:
            break
    environment["PYTHONPATH"] = ";".join(
        [
            str(source / "src"),
            str(root / ".tools/assistant-282-upstream/src/backend/base"),
            str(root / ".tools/assistant-282-upstream/src/lfx/src"),
        ]
    )
    environment["LAOMEDO_PROVIDER_SOURCE_WORKSPACE"] = str(source)
    environment["LAOMEDO_ASSISTANT_STORAGE_ROOT"] = str(private / "project-storage")
    environment.pop("LAOMEDO_PIN", None)
    entry = """from pathlib import Path
import os
import laomedo
import uvicorn
from laomedo.integrations.langflow.local_profiles.runtime import LocalProfileRuntime
from laomedo.integrations.langflow.viewer import create_app
components=os.environ.get('LANGFLOW_COMPONENTS_PATH')
if components: laomedo.__path__.append(str(Path(components)/'laomedo'))
runtime=LocalProfileRuntime(Path(os.environ['LANGFLOW_CONFIG_DIR']).parent, provider_source=Path(os.environ['LAOMEDO_PROVIDER_SOURCE_WORKSPACE']))
app=create_app(profile_runtime=runtime)
uvicorn.run(app,host='127.0.0.1',port=55753,access_log=False)
"""
    process.terminate()
    process.wait(timeout=20)
    with (private / "repository-storage-preview.log").open("ab") as output:
        child = subprocess.Popen(
            [str(root / ".venv/Scripts/python.exe"), "-u", "-c", entry],
            cwd=private,
            env=environment,
            stdout=output,
            stderr=output,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    (private / "repository-storage-preview-pid").write_text(
        str(child.pid), encoding="utf-8"
    )
    print(json.dumps({"preview_pid": child.pid, "base": base}))


if __name__ == "__main__":
    main()
