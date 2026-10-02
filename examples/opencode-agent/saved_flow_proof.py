"""One bounded model turn through the saved OpenCode flow, with no node tweaks."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import Request, urlopen

import flow_acceptance as f


EXPECTED_URL = "http://host.docker.internal:8768"
EXPECTED_SKILLS = {"laomedo-pilot", "laomedo-result-format"}
MARKER = "SAVED-FLOW-27"
COMMAND = (
    "for p in /controller-auth.json /home/runner/.agents/skills "
    "/home/runner/.local/share/opencode /home/runner/.config/opencode; "
    'do test ! -e "$p" || exit 42; done; '
    f"printf {MARKER} > /draft/saved-flow-marker.txt; "
    "ls -1 /draft/.agents/skills; cat /draft/fixture.txt"
)


def tracked_files(root):
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).split(b"\0")
    return [root / name.decode("utf-8") for name in names if name]


def private_credential_absent(data, key):
    return key not in data


def fixture_observed(events):
    return any(re.search(r"\bamber\b", event.get("stdout", ""), re.IGNORECASE) and
               re.search(r"\b3\b", event.get("stdout", "")) for event in events)


def verify_existing(run_id):
    """Correct a too-literal fixture predicate from stored evidence; no model call."""
    state = f.STATE
    old = json.loads((state / "saved-flow-proof-summary.json").read_text())
    if old["run_id"] != run_id or old["attempt_number"] != 13:
        raise RuntimeError("unexpected_saved_flow_run")
    path = state / "runs-state/runs" / run_id / "worker-events.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    selected = [event for event in events if event["command"] == COMMAND and event["exit_code"] == 0]
    if len(selected) != 1:
        raise RuntimeError("successful_exact_worker_command_not_found")
    if old["checks"]["fixture_reported_by_worker"]:
        raise RuntimeError("original_fixture_predicate_did_not_fail")
    corrected = json.loads(json.dumps(old))
    corrected["checks"]["fixture_reported_by_worker"] = fixture_observed(selected)
    auth_key = json.loads((state / "profile/auth.json").read_text())["opencode-go"]["key"].encode()
    export = state / "exported-flow.json"
    corrected["checks"]["selected_provider_key_absent_from_export"] = (
        export.is_file() and auth_key not in export.read_bytes())
    corrected["verification_note"] = (
        "The initial checker expected literal label 'color: amber'; the exact successful "
        "worker command returned the fixture sentence 'The sample color is amber. "
        "The sample count is 3.' The live run and raw event are unchanged.")
    f.opencode._json(state / "saved-flow-proof-verified.json", corrected)
    print(json.dumps(corrected))
    if not all(corrected["checks"].values()):
        raise RuntimeError("saved_flow_proof_incomplete")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved-model-turn", action="store_true")
    args = parser.parse_args()
    if not args.approved_model_turn:
        parser.error("explicit model-turn authorization required")

    state = f.STATE
    ledger = json.loads((state / "runs-state/turn-ledger.json").read_text())
    if ledger.get("attempted_turns") not in {11, 12} or ledger.get("max_authorized_turns") != 14:
        raise RuntimeError("unexpected_ledger_state")
    expected_attempt = ledger["attempted_turns"] + 1
    flow_id = json.loads((state / "flow-id.json").read_text())["flow_id"]
    token = f.helper.login()
    saved = f.helper.call(f.helper.BASE + "/api/v1/flows/" + flow_id, token=token)
    if saved["http"] != 200:
        raise RuntimeError("saved_flow_unavailable")
    graph = saved["body"]["data"]
    nodes = [node for node in graph["nodes"] if node["data"]["type"] == "LaomedoOpenCodeAgent"]
    if len(nodes) != 1 or len(graph["nodes"]) != 6 or len(graph["edges"]) != 5:
        raise RuntimeError("saved_flow_graph_changed")
    template = nodes[0]["data"]["node"]["template"]
    expected = {"operation": "fresh", "runner_url": EXPECTED_URL,
                "model": "opencode-go/gpt-6-luna", "effort": "default"}
    if any(template[name]["value"] != value for name, value in expected.items()):
        raise RuntimeError("saved_flow_settings_changed")
    if sum(node["data"]["type"] == "LaomedoSkill" for node in graph["nodes"]) != 2:
        raise RuntimeError("saved_flow_skill_edges_changed")

    key = f.helper.call(f.helper.BASE + "/api/v1/api_key/",
        {"name": "opencode-27-saved-flow-proof"}, token=token)
    if key["http"] not in {200, 201}:
        raise RuntimeError("local_langflow_api_key_unavailable")
    auth_key = json.loads((state / "profile/auth.json").read_text())["opencode-go"]["key"]
    if not isinstance(auth_key, str) or len(auth_key) < 20:
        raise RuntimeError("private_provider_key_invalid")
    if not private_credential_absent(json.dumps(saved["body"]), auth_key):
        raise RuntimeError("credential_in_saved_flow")

    records = state / "runs-state/runs"
    before = {path.name for path in records.iterdir() if path.is_dir()}
    task = ("Load laomedo-pilot and laomedo-result-format with their native skill tool. "
            "Then invoke laomedo_exec once with exactly the command below. It checks "
            "path presence without opening any private file, writes a harmless marker, "
            "lists only the offered skill names and reads the fixture. Do not append "
            "punctuation to the command. After the tool, report the marker and fixture "
            "result without printing credential contents.\n\n" + COMMAND)
    payload = {"input_value": task, "input_type": "chat", "output_type": "chat"}
    if "tweaks" in payload:
        raise AssertionError("saved_flow_request_contains_tweaks")
    response = f.helper.call(f.helper.BASE + "/api/v1/run/" + flow_id,
        payload, token=token, api_key=key["body"]["api_key"])
    f.opencode._json(state / "saved-flow-proof-response.json", response)
    created = {path.name for path in records.iterdir() if path.is_dir()} - before
    if len(created) != 1:
        raise RuntimeError("saved_flow_run_identity_ambiguous")
    run_id = next(iter(created))
    run = json.loads((records / run_id / "record.json").read_text())
    with urlopen(Request("http://127.0.0.1:8768/v1/runs/" + run_id), timeout=10) as retrieved:
        status = json.load(retrieved)
    workers = [json.loads(line) for line in (records / run_id / "worker-events.jsonl").read_text().splitlines()]
    selected = [event for event in workers if event["command"] == COMMAND]
    active_skills = {item["skill_id"] for item in run.get("skills", [])
                         if item.get("use_evidence") == "native_skill_tool_completed"}
    views = list((records / run_id).glob("controller-*/view/.agents/skills"))
    expected_refs = json.loads((state / "skill-references.json").read_text())["skills"]
    pinned_names = {item["skill_id"] for item in expected_refs}
    viewed_names = [{entry.name for entry in view.iterdir()} for view in views]
    marker = (records / run_id / "post-run/saved-flow-marker.txt")
    repo_roots = [f.ROOT, f.ROOT.parent / "work-opencode-specs.local"]
    tracked = [path for root in repo_roots for path in tracked_files(root)]
    private_artifacts = [records / run_id / "raw-events.jsonl", records / run_id / "worker-events.jsonl",
                         state / "saved-flow-proof-response.json"]
    key_bytes = auth_key.encode("utf-8")
    no_key_in_tracked = all(key_bytes not in path.read_bytes() for path in tracked if path.is_file())
    no_key_in_private_results = all(key_bytes not in path.read_bytes() for path in private_artifacts)
    checks = {
        "no_runner_override": True,
        "langflow_http_200": response["http"] == 200,
        "run_completed": run.get("status") == "completed",
        "expected_attempt": run.get("attempt_number") == expected_attempt,
        "status_query_matches": status.get("run_id") == run_id and status.get("status") == "completed",
        "both_skills_loaded_natively": active_skills == EXPECTED_SKILLS,
        "controller_views_only_pinned_skills": bool(views) and all(names == pinned_names for names in viewed_names),
        "worker_path_probe_succeeded": any(event.get("exit_code") == 0 for event in selected),
        "worker_listed_only_offered_skills": any(EXPECTED_SKILLS == set(event.get("stdout", "").splitlines()[:2]) for event in selected),
        "workspace_marker_verified": marker.is_file() and marker.read_text() == MARKER,
        "fixture_reported_by_worker": fixture_observed(selected),
        "selected_provider_key_absent_from_tracked_repos": no_key_in_tracked,
        "selected_provider_key_absent_from_run_results": no_key_in_private_results,
        "selected_provider_key_absent_from_saved_flow": True,
        "selected_provider_key_absent_from_export": (
            (state / "exported-flow.json").is_file() and
            key_bytes not in (state / "exported-flow.json").read_bytes()),
    }
    ledger_after = json.loads((state / "runs-state/turn-ledger.json").read_text())
    summary = {"run_id": run_id, "status": run.get("status"), "attempt_number": run.get("attempt_number"),
               "http": response["http"], "skill_ids": sorted(active_skills), "checks": checks,
               "ledger_after": ledger_after}
    f.opencode._json(state / "saved-flow-proof-summary.json", summary)
    print(json.dumps(summary))
    if not all(checks.values()):
        raise RuntimeError("saved_flow_proof_incomplete")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--verify-existing-run":
        verify_existing(sys.argv[2])
    else:
        main()
