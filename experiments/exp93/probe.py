"""One-shot, zero-model crash probe for the production lease integration."""

import json
from pathlib import Path
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
LABEL = "laomedo.experiment=exp93"
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
            "labels": entry["Config"]["Labels"] or {}}


def setup(root):
    (root / "repo" / ".git").mkdir(parents=True)
    source = root / "repo" / "source"
    source.mkdir()
    (source / "input.txt").write_text("synthetic", encoding="utf-8")
    skill = root / "input-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: fixture\n---\nSynthetic.\n",
                                   encoding="utf-8", newline="\n")
    revision = SkillStore(root / "skills").import_skill("fixture", skill)
    body = {"request_id": str(uuid4()), "task": "synthetic pre-initialization wait",
            "model": "synthetic-model", "effort": "low",
            "skill_ref": {"skill_id": "fixture", "revision_id": revision["revision_id"],
                          "tree_hash": revision["tree_hash"]}}
    (root / "body.json").write_text(json.dumps(body), encoding="utf-8")


def child(root):
    class CrashTransport:
        def __init__(self, command, evidence):
            name = command[command.index("--name") + 1]
            labels = [command[index + 1] for index, value in enumerate(command[:-1])
                      if value == "--label"]
            if len(labels) != 2 or not all("=" in value for value in labels):
                raise AssertionError("missing_exact_ownership_labels")
            result = docker("run", "-d", "--rm", "--pull=never", "--name", name,
                            "--label", LABEL, "--label", labels[0], "--label", labels[1],
                            "--network", "none", "--user", "10001:10001",
                            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                            IMAGE, "sleep", "120")
            value = inspect(name)
            if not value or value["id"] != result.stdout.strip() or not value["running"]:
                raise AssertionError("owned_container_not_running")
            (root / "container.json").write_text(json.dumps({"name": name, "id": value["id"]}),
                                                 encoding="utf-8")

        def request(self, method, params, timeout=30):
            time.sleep(120)
            raise AssertionError("unexpected_return")

    runner = LocalRunner(root / "state", root / "skills", root / "repo" / "source",
                         transport=CrashTransport, check_docker=False,
                         max_model_turns=0, supervise_containers=True)
    runner.start_async(json.loads((root / "body.json").read_text(encoding="utf-8")))
    time.sleep(120)


def safe_remove(name):
    entry = inspect(name)
    if entry is None:
        return
    if entry["name"] != name or entry["labels"].get("laomedo.experiment") != "exp93":
        raise RuntimeError("refuse_cleanup_unowned_container")
    docker("rm", "-f", entry["id"])


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "child":
        child(Path(sys.argv[2]).resolve())
        return
    if len(sys.argv) != 1:
        raise SystemExit("usage: python -m experiments.exp93.probe")
    if OUTPUT.exists():
        raise SystemExit("observation_exists_no_retry")
    if docker("image", "inspect", IMAGE, "--format", "{{.Id}}").stdout.strip() != IMAGE_ID:
        raise SystemExit("synthetic_image_id_changed")
    root = Path(tempfile.mkdtemp(prefix="laomedo-exp93-")).resolve()
    control_name = "laomedo-codex-" + uuid4().hex
    owned_name = None
    process = None
    observation = {"started_utc": utc(), "image_id": IMAGE_ID, "model_turns": 0,
                   "protocol_commit": "47c09ed", "runner_requests": 1}
    try:
        setup(root)
        control_id = docker("run", "-d", "--rm", "--pull=never", "--name", control_name,
                            "--label", LABEL, "--network", "none", "--user", "10001:10001",
                            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                            IMAGE, "sleep", "120").stdout.strip()
        process = subprocess.Popen([sys.executable, "-m", "experiments.exp93.probe",
                                    "child", str(root)], cwd=Path(__file__).resolve().parents[2],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        until = time.monotonic() + 20
        while time.monotonic() < until and not (root / "container.json").exists():
            if process.poll() is not None:
                raise RuntimeError("child_exited_before_container")
            time.sleep(.1)
        if not (root / "container.json").exists():
            raise RuntimeError("owned_container_start_timeout")
        created = json.loads((root / "container.json").read_text(encoding="utf-8"))
        owned_name = created["name"]
        before = inspect(owned_name)
        control = inspect(control_name)
        records = list((root / "state" / "runs").glob("*/record.json"))
        if len(records) != 1:
            raise RuntimeError("expected_one_saved_run")
        saved = json.loads(records[0].read_text(encoding="utf-8"))
        owner = saved.get("container_ownership") or {}
        if (not before or before["id"] != created["id"] or not before["running"] or
                before["labels"].get("laomedo.run_id") != saved["run_id"] or
                before["labels"].get("laomedo.launch_token") != owner.get("launch_token") or
                owner.get("name") != owned_name or not owner.get("supervised") or
                not control or control["id"] != control_id or not control["running"]):
            raise RuntimeError("prekill_identity_or_reservation_mismatch")
        observation.update(run_id=saved["run_id"], owned_name=owned_name,
                           owned_id=before["id"], control_name=control_name,
                           control_id=control_id, reservation_saved_before_kill=True)
        killed_at = time.monotonic()
        observation["kill_utc"] = utc()
        process.kill()
        process.wait(timeout=10)
        until = killed_at + 60
        while time.monotonic() < until and inspect(owned_name) is not None:
            time.sleep(.2)
        observation["owned_absent_after_kill"] = inspect(owned_name) is None
        observation["cleanup_elapsed_seconds_upper"] = round(time.monotonic() - killed_at, 3)
        control_after = inspect(control_name)
        observation["control_survived"] = bool(control_after and control_after["id"] == control_id
                                               and control_after["running"])
        restarted = LocalRunner(root / "state", root / "skills", root / "repo" / "source",
                                check_docker=False, max_model_turns=0)
        after = restarted.status(saved["run_id"])
        observation.update(after_restart_status=after["status"],
                           after_restart_error=after["error_category"],
                           cleanup_verified=after["container_ownership"].get("cleanup_verified"),
                           cleanup_detail=after["container_ownership"].get("cleanup_detail"),
                           turn_ledger_exists=(root / "state" / "turn-ledger.json").exists())
        if (not observation["owned_absent_after_kill"] or
                observation["cleanup_elapsed_seconds_upper"] > 60 or
                not observation["control_survived"] or
                observation["after_restart_status"] != "interrupted" or
                not observation["cleanup_verified"] or observation["turn_ledger_exists"]):
            raise AssertionError("lease_integration_check_failed")
    finally:
        if process and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        if owned_name:
            safe_remove(owned_name)
        safe_remove(control_name)
        observation["finished_utc"] = utc()
        OUTPUT.write_text(json.dumps(observation, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8", newline="\n")
        # Keep local private state for a failed run's investigation. Successful
        # disposable state is not part of the committed evidence.
        if observation.get("cleanup_verified") and observation.get("control_survived"):
            import shutil
            shutil.rmtree(root)
    print(json.dumps(observation, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
