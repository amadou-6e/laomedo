"""Freeze host-read issue/source inputs and proposed configuration; never dispatch.

This explicit command uses the selected host connection for repository reads.
It starts no runner, spends no model turn and performs no GitHub write.
"""
import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile

from laomedo.github_git_transport import GitHubGitTransport
from laomedo.github_rest_transport import GitHubRestTransport
from laomedo.git_workspace import _git_environment, _bounded_git
from laomedo.host_token_connection import HostTokenConnection
from laomedo.issue_context import fetch_context
from laomedo.local_runner import GIT_IMAGE_ID
from laomedo.siwc_auth import _outside_git
from laomedo.skill_store import SkillStore

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "ga84jog/laomedo-exp104-disposable-20261007"
IDENTITY = "exp139-20261012-b"
BRANCH = IDENTITY
LANGFLOW = "langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0"
CONNECTION = "exp139-20261011-a-github"  # Existing approved host connection.


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def connection(root, token_file):
    return HostTokenConnection(connection_id=CONNECTION, generation=1,
        repository=REPOSITORY, token_file=token_file, key="GH_LAOMEDO",
        forbidden_mount=root / "runner")


def prepare(root, token_file):
    root = _outside_git(root)
    root.mkdir(parents=True, exist_ok=False)
    provider = connection(root, token_file)
    rest = GitHubRestTransport(REPOSITORY, provider.token)
    reads = []
    def read(path):
        reads.append(path)
        return rest._call("GET", "/" + path, None, CONNECTION, 1,
                          allow_list="/timeline?" in path or path.endswith("/issues"))
    repo = read("repos/" + REPOSITORY)
    base = repo["default_branch"]
    listing = read("repos/" + REPOSITORY + "/issues")
    candidates = [item for item in listing["items"] if "pull_request" not in item]
    if not candidates:
        raise ValueError("existing_issue_required")
    number = min(item["number"] for item in candidates)
    # _call wraps list responses; fetch_context needs the underlying array.
    def issue_read(path):
        value = read(path)
        return value["items"] if "/timeline?" in path else value
    context = fetch_context(REPOSITORY, number, request=issue_read, max_timeline_pages=2)
    if context["related_prs_complete"] is not True:
        raise ValueError("complete_issue_context_required")
    snapshot = {"source": "host_frozen_github", "context": context,
        "snapshot_id": "sha256:" + sha256(json.dumps(context, sort_keys=True,
            separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()}
    source = root / "source"
    source.mkdir()
    git_transport = GitHubGitTransport(REPOSITORY, source, "0" * 40, provider.token)
    refs = git_transport._fetch({"action": "list"}, CONNECTION, 1, BRANCH, base)
    if any(item["ref"] == "refs/heads/" + BRANCH for item in refs["refs"]):
        raise ValueError("experiment_branch_exists")
    baseline = next(item["commit"] for item in refs["refs"] if item["ref"] == "refs/heads/" + base)
    fetched = git_transport._fetch({"action": "fetch", "ref": "refs/heads/" + base,
                                    "commit": baseline}, CONNECTION, 1, BRANCH, base)
    bundle = root / "baseline.bundle"
    bundle.write_bytes(base64.b64decode(fetched["bundle"], validate=True))
    with tempfile.TemporaryDirectory(prefix="exp139-git-home-") as home:
        environment = _git_environment(home)
        for args in (("init", "--template=", "--quiet"),
                     ("fetch", "--no-tags", str(bundle), "refs/heads/laomedo-read"),
                     ("checkout", "--quiet", "-b", base, baseline)):
            result = _bounded_git(["git", "-c", "core.hooksPath=" + home, "-C", str(source), *args], environment)
            if result.returncode:
                raise ValueError("baseline_checkout_failed")
    skill = SkillStore(root / "skill-store").import_skill("live-report",
        ROOT / "examples/langflow-workgraph-live/skill")
    body_hash = sha256(context["issue"]["body"].encode()).hexdigest()
    report = "\n".join(("# EXP-139 issue report", context["issue"]["url"],
                         "body_sha256: " + body_hash, snapshot["snapshot_id"], ""))
    task = ("Bounded demonstration, not arbitrary issue implementation. Read the selected skill and frozen issue. "
        "First call laomedo_output_precheck with a success submission missing report and observe rejection; "
        "then submit a success form with report='EXP-139 completed' and observe acceptance within this request. "
        "Create exactly experiments/exp139/issue-report.md with these exact UTF-8 bytes: " + json.dumps(report) + ". "
        "Create the parent folders. Set local Git author Laomedo Agent <agent@laomedo.local>. "
        "Commit only that report. Push exactly once using git push origin HEAD:refs/heads/" + BRANCH + ". "
        "Do not create a PR; downstream publication owns it. Do not retry an uncertain push. "
        "Finish with only the accepted JSON form; report failure honestly on any error.")
    tasks = {"success": task,
             "failure": "Do not edit files, use Git or access a remote. Return only "
                        "{\"task_outcome\":\"failure\",\"report\":\"Deliberate bounded failure route\"}.",
             "rejection": "Do not edit files, use Git or access a remote. Use the precheck then return only "
                          "{\"task_outcome\":\"success\",\"report\":\"Deliberate contract pin mismatch\"}."}
    inputs = root / "flow-input"
    inputs.mkdir()
    save(inputs / "inputs.json", {"snapshot": snapshot, "tasks": tasks})
    script = """import importlib.util,json
from pathlib import Path
spec=importlib.util.spec_from_file_location('live_builder','/work/examples/langflow-workgraph-live/build_flow.py')
builder=importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
data=json.loads(Path('/input/inputs.json').read_bytes())
for case,task in data['tasks'].items():
    flow=builder.build(data['snapshot'],task,runner_url='http://host.docker.internal:8779')
    if case=='rejection':
        node=next(n for n in flow['data']['nodes'] if n['id']=='contract')
        changed=json.loads(node['data']['node']['template']['requirements_json']['value'])
        changed['fields'][1]['checks']['min_length']=2
        node['data']['node']['template']['requirements_json']['value']=json.dumps(changed)
    Path('/input/'+case+'.json').write_text(json.dumps(flow,indent=2)+'\\n')
"""
    result = subprocess.run(["docker", "run", "--rm", "--pull=never", "--network", "none",
        "--mount", f"type=bind,source={ROOT},target=/work,readonly",
        "--mount", f"type=bind,source={inputs},target=/input", "--env", "PYTHONPATH=/work",
        "--entrypoint", "python", LANGFLOW, "-c", script], capture_output=True, timeout=60)
    if result.returncode:
        raise ValueError("graph_export_failed")
    save(root / "config.json", {"identity": IDENTITY, "repository": REPOSITORY,
        "branch": BRANCH, "base": base, "baseline": baseline, "turn_cap": 4,
        "runner_port": 8779, "handoff_seconds": 600, "token_file": str(token_file.resolve()),
        "connection_id": CONNECTION, "connection_generation": 1,
        "baseline_sha256": sha256(bundle.read_bytes()).hexdigest(),
        "report_sha256": sha256(report.encode()).hexdigest(),
        "skill": {key: skill[key] for key in ("skill_id", "revision_id", "tree_hash")}})
    save(root / "preparation.json", {"model_turns": 0, "github_writes": 0,
        "host_read_paths": reads, "git_reads": ["selected_ref_listing", "baseline_bundle_fetch"],
        "graph_hashes": {case: sha256((inputs / (case + ".json")).read_bytes()).hexdigest() for case in tasks},
        "issue_snapshot": snapshot["snapshot_id"], "agent_image": GIT_IMAGE_ID, "langflow_image": LANGFLOW})
    return {"identity": IDENTITY, "state": str(root), "model_turns": 0,
            "github_writes": 0, "configuration": "draft_not_activated"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.state.resolve(), args.token_file.resolve())))
    except Exception as failure:
        print(json.dumps({"status": "preparation_failed", "error_class": type(failure).__name__}))
        raise SystemExit(1)
