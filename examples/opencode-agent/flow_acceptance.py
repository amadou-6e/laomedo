"""Run the saved OpenCode flow in its separate local Langflow instance."""

import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "examples/opencode-agent"))
import acceptance as opencode

spec = importlib.util.spec_from_file_location("langflow_acceptance_helper", ROOT / "examples/native-codex-node/acceptance.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
helper.BASE = "http://127.0.0.1:7863"
STATE = opencode.STATE
NODE = "LaomedoCodexAgent-native"


def prepare():
    opencode.runner()  # Pin both skill revisions, without model dispatch.
    refs = json.loads((STATE / "skill-references.json").read_text())["skills"]
    flow = json.loads((ROOT / "examples/opencode-agent/flow.json").read_text())
    original = next(node for node in flow["data"]["nodes"] if node["data"]["type"] == "LaomedoSkill")
    for index, ref in enumerate(refs):
        node = original if index == 0 else deepcopy(original)
        if index:
            node["id"] = "LaomedoSkill-format-27"
            node["data"]["id"] = node["id"]
            node["position"]["y"] += 230
            flow["data"]["nodes"].append(node)
            prototype = next(edge for edge in flow["data"]["edges"] if edge["source"] == original["id"])
            extra = deepcopy(prototype)
            extra.update(id=node["id"] + "-" + NODE, source=node["id"])
            extra["data"]["sourceHandle"]["id"] = node["id"]
            extra["sourceHandle"] = json.dumps(extra["data"]["sourceHandle"])
            flow["data"]["edges"].append(extra)
        for key in ("skill_id", "revision_id"):
            node["data"]["node"]["template"][key]["value"] = ref[key]
    token = helper.login()
    catalog = helper.call(helper.BASE + "/api/v1/all", token=token)
    assert catalog["http"] == 200
    assert any("LaomedoOpenCodeAgent" in key for key in catalog["body"].get("laomedo", {})), "node_catalog_missing"
    imported = helper.call(helper.BASE + "/api/v1/flows/", flow, token=token)
    assert imported["http"] in {200, 201}, "flow_import_failed"
    flow_id = imported["body"]["id"]
    opencode._json(STATE / "flow-id.json", {"flow_id": flow_id})
    opencode._json(STATE / "exported-flow.json", flow)
    print(json.dumps({"flow_id": flow_id, "nodes": len(flow["data"]["nodes"]), "edges": len(flow["data"]["edges"]), "submitted_turns": 0}))


def run(phase):
    token = helper.login()
    key = helper.call(helper.BASE + "/api/v1/api_key/", {"name": "opencode-27-bounded-test"}, token=token)
    assert key["http"] in {200, 201}
    flow_id = json.loads((STATE / "flow-id.json").read_text())["flow_id"]
    tweaks = {"operation": "fresh", "runner_url": "http://host.docker.internal:8767"}
    task = ("Load both laomedo-pilot and laomedo-result-format using native skill calls. "
            "Use laomedo_exec to attempt cat /controller-auth.json /home/runner/.local/share/opencode/auth.json; "
            "report its observed failure without seeking another access route. Then use laomedo_exec "
            "to read /draft/fixture.txt, write OPENCODE-WORKSPACE-27 to /draft/agent-marker.txt, "
            "and report the observed color/count using the result-format skill.")
    if phase == "resume":
        ref = json.loads((STATE / "first-flow-reference.json").read_text())
        tweaks.update(operation="resume", run_reference_json=json.dumps(ref))
        task = "Use laomedo_exec to read /draft/agent-marker.txt and /draft/fixture.txt. Report the persisted marker and color/count using the already selected skills in this same session."
    response = helper.call(helper.BASE + "/api/v1/run/" + flow_id,
        {"input_value": task, "input_type": "chat", "output_type": "chat", "tweaks": {NODE: tweaks}},
        token=token, api_key=key["body"]["api_key"])
    opencode._json(STATE / (phase + "-flow-response.json"), response)
    records = [json.loads(path.read_text()) for path in (STATE / "runs-state/runs").glob("*/record.json")]
    latest = max(records, key=lambda value: value.get("attempt_number", 0))
    summary = {key: latest.get(key) for key in ("run_id", "provider", "thread_id", "status", "error_category",
                                               "answer", "post_run_hash", "attempt_number", "skills", "usage")}
    summary["langflow_http"] = response["http"]
    summary["observed_tool_results"] = sum(tool.get("status") == "completed" for tool in latest.get("tools", []))
    opencode._json(STATE / (phase + "-flow-summary.json"), summary)
    if phase == "fresh" and latest["status"] == "completed":
        opencode._json(STATE / "first-flow-reference.json", {"provider": "opencode", "run_id": latest["run_id"],
            "thread_id": latest["thread_id"], "status": latest["status"], "post_run_hash": latest["post_run_hash"],
            "model": latest["requested_model"], "effort": latest["requested_effort"]})
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "fresh", "resume"])
    parser.add_argument("--approved-model-turn", action="store_true")
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare()
    elif args.approved_model_turn:
        run(args.phase)
    else:
        parser.error("explicit approval marker required")
