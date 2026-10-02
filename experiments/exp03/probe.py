"""Edit a saved Langflow flow while its first synthetic stage is paused."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from threading import Thread
import time
from urllib import request


HERE = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:17863"
TOKEN = None


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def api(method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    req = request.Request(BASE + path, data=data, method=method, headers=headers)
    with request.urlopen(req, timeout=150) as response:
        return json.load(response)


def main():
    global TOKEN
    TOKEN = api("GET", "/api/v1/auto_login")["access_token"]
    gate = HERE / "release"
    entered = HERE / "release.entered"
    for item in (gate, entered):
        item.unlink(missing_ok=True)
    flow = json.loads((HERE / "flow.json").read_text(encoding="utf-8"))
    created = api("POST", "/api/v1/flows/", flow)
    flow_id = created["id"]
    before = api("GET", f"/api/v1/flows/{flow_id}")
    graph_before = digest(before["data"])
    marker_before = next(n for n in before["data"]["nodes"] if n["id"] == "Exp03Marker-exp03")
    code_before = sha256(marker_before["data"]["node"]["template"]["code"]["value"].encode()).hexdigest()
    run = {}

    def invoke():
        try:
            run["response"] = api("POST", "/api/v1/run/session/" + flow_id,
                                  {"input_value": "TASK", "input_type": "chat", "output_type": "chat"})
        except Exception as exc:
            run["error"] = str(exc)

    thread = Thread(target=invoke, daemon=True)
    thread.start()
    deadline = time.monotonic() + 75
    while not entered.exists() and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.1)
    if not entered.exists():
        raise RuntimeError("pause stage was not entered: " + json.dumps(run))
    modified = deepcopy(before)
    marker = next(n for n in modified["data"]["nodes"] if n["id"] == "Exp03Marker-exp03")
    marker["data"]["node"]["template"]["marker"]["value"] = "AFTER"
    code = marker["data"]["node"]["template"]["code"]["value"]
    marker["data"]["node"]["template"]["code"]["value"] = code.replace("}|{self.marker}", "}|EDITED-{self.marker}")
    updated = api("PATCH", f"/api/v1/flows/{flow_id}", {"data": modified["data"]})
    graph_after = digest(updated["data"])
    marker_after = next(n for n in updated["data"]["nodes"] if n["id"] == "Exp03Marker-exp03")
    code_after = sha256(marker_after["data"]["node"]["template"]["code"]["value"].encode()).hexdigest()
    gate.write_text("release", encoding="utf-8")
    thread.join(90)
    second = api("POST", "/api/v1/run/session/" + flow_id,
                 {"input_value": "TASK", "input_type": "chat", "output_type": "chat"})
    report = {"image": "langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0",
              "flow_id": flow_id, "graph_before_sha256": graph_before,
              "graph_after_sha256": graph_after, "component_before_sha256": code_before,
              "component_after_sha256": code_after, "pause_entered": True,
              "run_finished": not thread.is_alive(), "run": run,
              "next_run": second}
    (HERE / "observation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    gate.unlink(missing_ok=True)
    entered.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
