"""EXP-91: one hard runner kill with a labelled, synthetic Docker container."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from uuid import uuid4

from laomedo.local_runner import LocalRunner
from laomedo.skill_store import SkillStore


IMAGE = "python:3.9-slim"
IMAGE_ID = "sha256:bb8009c87ab69e751a1dd2c6c7f8abaae3d9fce8e072802d4a23c95594d16d84"
LABEL = "laomedo.experiment=exp91"
OUTPUT = Path(__file__).with_name("observation.json")


def utc():
    return datetime.now(timezone.utc).isoformat()


def docker(*args, check=True):
    return subprocess.run(["docker", *args], capture_output=True, text=True,
                          timeout=20, check=check)


def inspect(name):
    result = docker("inspect", name, check=False)
    if result.returncode:
        return None
    entry = json.loads(result.stdout)[0]
    return {"id": entry["Id"], "name": entry["Name"].lstrip("/"),
            "running": entry["State"]["Running"],
            "experiment_label": entry["Config"]["Labels"].get("laomedo.experiment")}


def setup(root):
    (root / "repo" / ".git").mkdir(parents=True)
    source = root / "repo" / "source"
    source.mkdir()
    (source / "input.txt").write_text("synthetic", encoding="utf-8")
    skill = root / "input-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: fixture\n---\nSynthetic.\n",
                                   encoding="utf-8", newline="\n")
    store = SkillStore(root / "skills")
    revision = store.import_skill("fixture", skill)
    body = {"request_id": str(uuid4()), "task": "synthetic pre-initialization wait",
            "model": "synthetic-model", "effort": "low",
            "skill_ref": {"skill_id": "fixture", "revision_id": revision["revision_id"],
                          "tree_hash": revision["tree_hash"]}}
    (root / "body.json").write_text(json.dumps(body), encoding="utf-8")


def child(root):
    class CrashTransport:
        def __init__(self, command, evidence):
            name = command[command.index("--name") + 1]
            if not re.fullmatch(r"laomedo-codex-[0-9a-f]{32}", name):
                raise AssertionError("unexpected_container_name")
            result = docker("run", "-d", "--rm", "--pull=never", "--name", name,
                            "--label", LABEL, "--network", "none", "--user", "10001:10001",
                            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                            IMAGE, "sleep", "120")
            value = inspect(name)
            if value is None or value["id"] != result.stdout.strip() or not value["running"]:
                raise AssertionError("container_not_running")
            (root / "container.json").write_text(json.dumps({"name": name, "id": value["id"]}),
                                                 encoding="utf-8")

        def request(self, method, params, timeout=30):
            # The child is killed while blocked on initialize, before any turn.
            time.sleep(120)
            raise AssertionError("unexpected_return")

    runner = LocalRunner(root / "state", root / "skills", root / "repo" / "source",
                         transport=CrashTransport, check_docker=False, max_model_turns=0)
    body = json.loads((root / "body.json").read_text(encoding="utf-8"))
    runner.start_async(body)
    time.sleep(120)


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "child":
        child(Path(sys.argv[2]).resolve())
        return
    if len(sys.argv) != 1:
        raise SystemExit("usage: python -m experiments.exp91.probe")
    if OUTPUT.exists():
        raise SystemExit("observation_exists_no_retry")
    image_id = docker("image", "inspect", IMAGE, "--format", "{{.Id}}").stdout.strip()
    if image_id != IMAGE_ID:
        raise SystemExit("synthetic_image_id_changed")
    root = Path(tempfile.mkdtemp(prefix="laomedo-exp91-")).resolve()
    if root.parent != Path(tempfile.gettempdir()).resolve() or not root.name.startswith("laomedo-exp91-"):
        raise RuntimeError("unsafe_temporary_root")
    observation = {"probe_started_utc": utc(), "source_base": "f7a83f0",
                   "image": IMAGE, "image_id": image_id, "model_turns": 0,
                   "runner_requests": 1, "container_removal_scope": "exact_name_and_label_only"}
    process = None
    name = None
    try:
        setup(root)
        process = subprocess.Popen([sys.executable, "-m", "experiments.exp91.probe",
                                    "child", str(root)], cwd=Path(__file__).resolve().parents[2],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        until = time.monotonic() + 20
        while time.monotonic() < until and not (root / "container.json").exists():
            if process.poll() is not None:
                raise RuntimeError("child_exited_before_container")
            time.sleep(.1)
        if not (root / "container.json").exists():
            raise RuntimeError("container_start_timeout")
        control = json.loads((root / "container.json").read_text(encoding="utf-8"))
        name = control["name"]
        before = inspect(name)
        if before is None or before["id"] != control["id"] or before["experiment_label"] != "exp91":
            raise RuntimeError("container_identity_mismatch_before_kill")
        records = list((root / "state" / "runs").glob("*/record.json"))
        if len(records) != 1:
            raise RuntimeError("expected_one_saved_run")
        saved = json.loads(records[0].read_text(encoding="utf-8"))
        if saved["status"] != "running":
            raise RuntimeError("run_not_active_before_kill")
        observation.update(run_id=saved["run_id"], container_name=name,
                           container_id=before["id"], before_kill_status=saved["status"],
                           before_kill_container_running=before["running"],
                           container_name_in_saved_record=name in json.dumps(saved))
        observation["kill_utc"] = utc()
        process.kill()
        process.wait(timeout=10)
        observation["child_exit_code"] = process.returncode
        restarted = LocalRunner(root / "state", root / "skills", root / "repo" / "source",
                                check_docker=False, max_model_turns=0)
        after_record = restarted.status(saved["run_id"])
        after_container = inspect(name)
        observation.update(after_restart_utc=utc(),
                           after_restart_status=after_record["status"],
                           after_restart_error=after_record["error_category"],
                           after_restart_container_running=bool(after_container and after_container["running"]),
                           after_restart_container_id=after_container["id"] if after_container else None,
                           after_restart_container_label=after_container["experiment_label"] if after_container else None,
                           turn_ledger_exists=(root / "state" / "turn-ledger.json").exists())
        if after_record["status"] != "interrupted" or not after_container or not after_container["running"]:
            raise AssertionError("unexpected_crash_boundary_result")
        if name in json.dumps(after_record) or observation["turn_ledger_exists"]:
            raise AssertionError("unexpected_durable_identity_or_turn")
    finally:
        if process and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        if name:
            target = inspect(name)
            if target:
                if target["name"] != name or target["experiment_label"] != "exp91":
                    raise RuntimeError("refuse_cleanup_unowned_container")
                docker("rm", "-f", name)
            observation["exact_container_absent_after_cleanup"] = inspect(name) is None
        observation["probe_finished_utc"] = utc()
        OUTPUT.write_text(json.dumps(observation, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8", newline="\n")
        shutil.rmtree(root)
    print(json.dumps(observation, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
